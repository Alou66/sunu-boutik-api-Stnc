"""Caractérise le verrouillage de InvoiceService.update (étape 0.1.4) et l'ordre
d'acquisition des verrous produits de _apply_lines (étape 0.1.7).

Comme test_concurrency.py, les scénarios de course lancent de vraies requêtes
HTTP en parallèle (threads + barrier, un TestClient par thread) contre le
Postgres local : les verrous FOR UPDATE ne sont exercés que par de vraies
transactions concurrentes.

Réf. app/modules/billing/billing_service.py::InvoiceService.update /
_lock_products_in_order, app/modules/payments/payments_service.py::create.
"""
import threading
import time
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.db.session import SessionLocal, engine
from app.main import app
from app.modules.billing.billing_model import Invoice
from app.modules.billing.billing_repository import InvoiceRepository
from app.modules.payments.payments_model import Payment
from app.modules.products.products_model import Product


def _run_parallel(targets_and_args):
    barrier = threading.Barrier(len(targets_and_args))
    threads = [threading.Thread(target=fn, args=(*args, barrier)) for fn, args in targets_and_args]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "un thread est resté bloqué (deadlock ou verrou jamais relâché)"


def _request(results, index, method, headers, path, json, barrier):
    with TestClient(app) as local_client:
        barrier.wait(timeout=5)
        results[index] = local_client.request(method, path, headers=headers, json=json)


def _create_invoice(client, auth_headers, lines):
    resp = client.post("/invoices", headers=auth_headers, json={"lines": lines})
    assert resp.status_code == 201, resp.text
    return resp.json()


@contextmanager
def _slow_product_locks(delay=0.25):
    """Ralentit chaque SELECT ... FOR UPDATE sur products (après acquisition du
    verrou) pour élargir la fenêtre de course : sans ordre de verrouillage
    cohérent, deux transactions croisées se bloquent alors de façon fiable au
    lieu d'un deadlock aléatoire."""

    def _sleep_after_lock(conn, cursor, statement, parameters, context, executemany):
        if "FOR UPDATE" in statement and "FROM products" in statement:
            time.sleep(delay)

    event.listen(engine, "after_cursor_execute", _sleep_after_lock)
    try:
        yield
    finally:
        event.remove(engine, "after_cursor_execute", _sleep_after_lock)


def _second_product(db_session, shop, category, name="Sucre 1kg", quantity=50):
    product = Product(shop_id=shop.id, category_id=category.id, name=name, unit_price=700, quantity=quantity)
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


# ---- 0.1.4 : InvoiceService.update verrouille la facture ----


def test_update_sees_payment_committed_while_it_was_waiting_for_the_invoice_lock(
    client, auth_headers, db_session, owner, shop, simple_product
):
    """Un paiement est en cours (verrou facture tenu, non commité) quand la
    modification arrive. La modification doit attendre le verrou puis relire
    amount_paid : elle est alors refusée en 400, et ne doit surtout pas écraser
    le total sous le montant déjà encaissé (violation de
    ck_invoices_amount_paid_lte_total, donc 500, avec une lecture sans verrou)."""
    invoice = _create_invoice(client, auth_headers, [{"product_id": simple_product.id, "quantity": 1}])
    assert invoice["total"] == 15000

    holder = SessionLocal()
    result = {}

    def _patch_invoice():
        try:
            with TestClient(app) as local_client:
                started.set()
                result["response"] = local_client.patch(
                    f"/invoices/{invoice['id']}",
                    headers=auth_headers,
                    json={"lines": [{"product_id": simple_product.id, "quantity": 1, "unit_price": 5000}]},
                )
        except Exception as exc:  # noqa: BLE001 - on veut voir l'échec (500) dans l'assertion
            result["error"] = exc

    try:
        locked = InvoiceRepository(holder).get_by_id_locked(shop.id, invoice["id"])
        holder.add(Payment(shop_id=shop.id, invoice_id=locked.id, amount=15000, created_by_id=owner.id))
        holder.flush()
        locked.amount_paid = 15000

        started = threading.Event()
        thread = threading.Thread(target=_patch_invoice)
        thread.start()
        assert started.wait(timeout=5)
        time.sleep(0.6)  # laisse la requête PATCH atteindre (et attendre) le verrou de la facture
        holder.commit()  # le paiement est enfin commité, le verrou relâché
        thread.join(timeout=15)
    finally:
        holder.close()

    assert "error" not in result, result.get("error")
    response = result["response"]
    assert response.status_code == 400, response.text
    assert "déjà reçu un paiement" in response.json()["detail"]

    db_session.expire_all()
    stored = db_session.query(Invoice).filter(Invoice.id == invoice["id"]).one()
    assert stored.total == 15000
    assert stored.amount_paid == 15000
    db_session.refresh(simple_product)
    assert simple_product.quantity == 9  # le stock n'a pas été touché par la modification refusée


def test_concurrent_invoice_update_and_payment_keep_invariants(client, auth_headers, db_session, simple_product):
    """Thread A modifie la facture (total 15000 -> 5000), thread B encaisse 15000
    en même temps. Deux issues valides, jamais de mélange :
      - A passe d'abord : la facture vaut 5000, le paiement de 15000 dépasse le solde (400) ;
      - B passe d'abord : le paiement est enregistré, la modification est refusée (400).
    Dans les deux cas amount_paid <= total et amount_paid == somme des paiements actifs."""
    for round_number in range(4):
        invoice = _create_invoice(client, auth_headers, [{"product_id": simple_product.id, "quantity": 1}])
        results = {}
        _run_parallel(
            [
                (
                    _request,
                    (
                        results, 0, "PATCH", auth_headers, f"/invoices/{invoice['id']}",
                        {"lines": [{"product_id": simple_product.id, "quantity": 1, "unit_price": 5000}]},
                    ),
                ),
                (
                    _request,
                    (results, 1, "POST", auth_headers, f"/invoices/{invoice['id']}/payments", {"amount": 15000}),
                ),
            ]
        )
        update_status, payment_status = results[0].status_code, results[1].status_code
        assert (update_status, payment_status) in {(200, 400), (400, 201)}, (
            round_number, {i: (r.status_code, r.text) for i, r in results.items()},
        )

        db_session.expire_all()
        stored = db_session.query(Invoice).filter(Invoice.id == invoice["id"]).one()
        active_payments = (
            db_session.query(Payment).filter(Payment.invoice_id == invoice["id"], Payment.voided_at.is_(None)).all()
        )
        assert stored.amount_paid == sum(p.amount for p in active_payments)
        assert stored.amount_paid <= stored.total + 0.01
        if update_status == 200:
            assert stored.total == 5000 and active_payments == []
        else:
            assert stored.total == 15000 and stored.amount_paid == 15000


# ---- 0.1.7 : verrous produits acquis par product_id croissant ----


def test_crossed_product_order_sales_do_not_deadlock(client, auth_headers, db_session, shop, category, simple_product):
    """Transaction A : produit 1 + produit 2 ; transaction B : produit 2 + produit 1,
    lancées en parallèle (créations de facture)."""
    other = _second_product(db_session, shop, category)
    lines_a = [{"product_id": simple_product.id, "quantity": 1}, {"product_id": other.id, "quantity": 1}]
    lines_b = [{"product_id": other.id, "quantity": 1}, {"product_id": simple_product.id, "quantity": 1}]

    results = {}
    with _slow_product_locks():
        _run_parallel(
            [
                (_request, (results, 0, "POST", auth_headers, "/invoices", {"lines": lines_a})),
                (_request, (results, 1, "POST", auth_headers, "/invoices", {"lines": lines_b})),
            ]
        )

    assert [results[0].status_code, results[1].status_code] == [201, 201], {i: r.text for i, r in results.items()}
    db_session.refresh(simple_product)
    db_session.refresh(other)
    assert simple_product.quantity == 8
    assert other.quantity == 48


def test_crossed_product_order_updates_do_not_deadlock(client, auth_headers, db_session, shop, category, simple_product):
    """Deux modifications de factures DIFFÉRENTES (donc sans verrou de facture
    commun) portant sur les mêmes produits dans des ordres opposés : c'est le
    chemin où un deadlock reste possible, create() étant sérialisé par le verrou
    de la boutique. Sans tri par product_id, chaque transaction tient un produit
    et attend l'autre (Postgres en annule une : 409)."""
    other = _second_product(db_session, shop, category)
    lines_a = [{"product_id": simple_product.id, "quantity": 1}, {"product_id": other.id, "quantity": 1}]
    lines_b = [{"product_id": other.id, "quantity": 2}, {"product_id": simple_product.id, "quantity": 2}]
    invoice_a = _create_invoice(client, auth_headers, lines_a)
    invoice_b = _create_invoice(client, auth_headers, lines_b)

    results = {}
    with _slow_product_locks():
        _run_parallel(
            [
                (_request, (results, 0, "PATCH", auth_headers, f"/invoices/{invoice_a['id']}", {"lines": lines_a})),
                (_request, (results, 1, "PATCH", auth_headers, f"/invoices/{invoice_b['id']}", {"lines": lines_b})),
            ]
        )

    assert [results[0].status_code, results[1].status_code] == [200, 200], {i: r.text for i, r in results.items()}
    db_session.refresh(simple_product)
    db_session.refresh(other)
    # Stock initial 10 / 50 ; deux factures (1+2 unités de chaque) inchangées par les PATCH identiques.
    assert simple_product.quantity == 7
    assert other.quantity == 47


def test_update_keeps_invoice_line_order_and_stock_logic(client, auth_headers, db_session, shop, category, simple_product):
    """Le tri des verrous ne doit pas réordonner les lignes de la facture."""
    other = _second_product(db_session, shop, category)
    invoice = _create_invoice(
        client, auth_headers,
        [{"product_id": other.id, "quantity": 2}, {"product_id": simple_product.id, "quantity": 3}],
    )
    assert [line["product_id"] for line in invoice["lines"]] == [other.id, simple_product.id]

    resp = client.patch(
        f"/invoices/{invoice['id']}",
        headers=auth_headers,
        json={"lines": [{"product_id": other.id, "quantity": 4}, {"product_id": simple_product.id, "quantity": 1}]},
    )
    assert resp.status_code == 200, resp.text
    assert [line["product_id"] for line in resp.json()["lines"]] == [other.id, simple_product.id]

    db_session.refresh(simple_product)
    db_session.refresh(other)
    assert other.quantity == 46  # 50 - 4
    assert simple_product.quantity == 9  # 10 - 1


def test_update_unknown_invoice_still_returns_404(client, auth_headers, simple_product):
    resp = client.patch(
        "/invoices/999999",
        headers=auth_headers,
        json={"lines": [{"product_id": simple_product.id, "quantity": 1}]},
    )
    assert resp.status_code == 404
