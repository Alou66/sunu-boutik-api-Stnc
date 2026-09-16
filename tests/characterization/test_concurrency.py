"""Tests de concurrence multi-utilisateurs (audit ADMIN/EMPLOYEE simultanés).

Complète tests/characterization/test_invoice_concurrency.py (survente sur
facture + numérotation) avec les autres scénarios identifiés dans l'audit :
double soumission (idempotence), transformations concurrentes, vente et
approvisionnement simultanés sur le même article, double validation d'un
approvisionnement, double annulation d'une facture.

Chaque test lance deux requêtes HTTP réellement en parallèle (threads +
barrier, un TestClient par thread) contre la même base Postgres locale, pour
exercer les verrous FOR UPDATE / contraintes UNIQUE comme le ferait deux
employés cliquant en même temps depuis deux postes différents.
"""
import threading

from fastapi.testclient import TestClient

from app.main import app


def _run_parallel(targets_and_args):
    """Lance N fonctions en parallèle (synchronisées par une barrière commune)
    et attend qu'elles se terminent toutes."""
    barrier = threading.Barrier(len(targets_and_args))
    threads = [
        threading.Thread(target=fn, args=(*args, barrier))
        for fn, args in targets_and_args
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)


def _post(results, index, headers, path, json, barrier):
    with TestClient(app) as local_client:
        barrier.wait(timeout=5)
        results[index] = local_client.post(path, headers=headers, json=json)


# ---- Double soumission (idempotence) ----


def test_concurrent_invoice_creation_same_idempotency_key_creates_only_one_invoice(
    client, auth_headers, db_session, simple_product
):
    results = {}
    payload = {
        "lines": [{"product_id": simple_product.id, "quantity": 2}],
        "idempotency_key": "double-clic-facture-1",
    }
    _run_parallel(
        [
            (_post, (results, 0, auth_headers, "/invoices", payload)),
            (_post, (results, 1, auth_headers, "/invoices", payload)),
        ]
    )

    assert all(r.status_code == 201 for r in results.values()), {i: r.text for i, r in results.items()}
    assert results[0].json()["id"] == results[1].json()["id"], "les deux réponses doivent pointer sur la même facture"

    invoices = client.get("/invoices", headers=auth_headers).json()
    assert invoices["total"] == 1, "une seule facture ne doit avoir été créée"

    db_session.refresh(simple_product)
    assert simple_product.quantity == 8  # 10 - 2, décrémenté une seule fois


def test_concurrent_transformation_same_idempotency_key_creates_only_one_log(
    client, auth_headers, db_session, transformable_product
):
    results = {}
    payload = {
        "product_id": transformable_product.id,
        "direction": "to_secondaire",
        "quantity": 1,
        "idempotency_key": "double-clic-transfo-1",
    }
    _run_parallel(
        [
            (_post, (results, 0, auth_headers, "/transformations/execute", payload)),
            (_post, (results, 1, auth_headers, "/transformations/execute", payload)),
        ]
    )

    assert all(r.status_code == 201 for r in results.values()), {i: r.text for i, r in results.items()}
    assert results[0].json()["log"]["id"] == results[1].json()["log"]["id"]

    history = client.get("/transformations/history", headers=auth_headers).json()
    assert history["total"] == 1, "une seule transformation ne doit avoir été journalisée"

    db_session.refresh(transformable_product)
    # quantity=3 au départ, une seule conversion de 1 carton -> 4 seaux appliquée
    assert transformable_product.quantity == 2
    assert transformable_product.quantity_secondaire == 4


# ---- Transformations concurrentes sur le même article ----


def test_concurrent_transformations_never_oversell(client, auth_headers, db_session, transformable_product):
    transformable_product.quantity = 1
    db_session.commit()

    results = {}
    payload = {"product_id": transformable_product.id, "direction": "to_secondaire", "quantity": 1}
    _run_parallel(
        [
            (_post, (results, 0, auth_headers, "/transformations/execute", payload)),
            (_post, (results, 1, auth_headers, "/transformations/execute", payload)),
        ]
    )

    statuses = sorted(r.status_code for r in results.values())
    assert statuses == [201, 400], statuses
    failed = next(r for r in results.values() if r.status_code == 400)
    assert "Stock insuffisant" in failed.json()["detail"]

    db_session.refresh(transformable_product)
    assert transformable_product.quantity == 0
    assert transformable_product.quantity_secondaire == 4  # une seule transformation appliquée


# ---- Vente + approvisionnement simultanés sur le même article ----


def test_concurrent_sale_and_stock_receipt_validation_final_stock_is_correct(
    client, auth_headers, db_session, simple_product
):
    receipt = client.post(
        "/stock-receipts",
        headers=auth_headers,
        json={
            "supplier_id": None,
            "reference": "BL-CONC-1",
            "note": None,
            "lines": [{"product_id": simple_product.id, "unit_target": "principale", "quantity": 10, "unit_cost": 1000}],
        },
    ).json()

    results = {}

    def _validate_receipt(barrier):
        with TestClient(app) as local_client:
            barrier.wait(timeout=5)
            results["receipt"] = local_client.post(f"/stock-receipts/{receipt['id']}/validate", headers=auth_headers)

    def _sell(barrier):
        with TestClient(app) as local_client:
            barrier.wait(timeout=5)
            results["invoice"] = local_client.post(
                "/invoices",
                headers=auth_headers,
                json={"lines": [{"product_id": simple_product.id, "quantity": 3}]},
            )

    barrier = threading.Barrier(2)
    threads = [threading.Thread(target=_validate_receipt, args=(barrier,)), threading.Thread(target=_sell, args=(barrier,))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    # Deux transactions qui verrouillent le même article en FOR UPDATE
    # peuvent, dans de rares cas, se retrouver en deadlock Postgres (les deux
    # insertions dépendantes — InvoiceLine/StockMovement — re-sollicitent la
    # même ligne produit via leur clé étrangère). Postgres détecte alors le
    # cycle et annule l'une des deux transactions ; l'API renvoie ce conflit
    # comme un 409 propre et rejouable (voir app/main.py::db_conflict_handler)
    # plutôt qu'une 500 brute ou une donnée corrompue. Un client réel rejoue
    # simplement l'opération perdante, ce qu'on simule ici.
    for key in ("receipt", "invoice"):
        if results[key].status_code == 409:
            if key == "receipt":
                results[key] = client.post(f"/stock-receipts/{receipt['id']}/validate", headers=auth_headers)
            else:
                results[key] = client.post(
                    "/invoices",
                    headers=auth_headers,
                    json={"lines": [{"product_id": simple_product.id, "quantity": 3}]},
                )

    assert results["receipt"].status_code == 200, results["receipt"].text
    assert results["invoice"].status_code == 201, results["invoice"].text

    db_session.refresh(simple_product)
    # Stock initial 10, +10 (réception) -3 (vente) = 17, quel que soit l'ordre
    # d'exécution réel des deux transactions concurrentes.
    assert simple_product.quantity == 17


# ---- Double validation / double annulation ----


def test_concurrent_stock_receipt_validation_only_one_succeeds(client, auth_headers, db_session, simple_product):
    receipt = client.post(
        "/stock-receipts",
        headers=auth_headers,
        json={
            "supplier_id": None,
            "reference": "BL-CONC-2",
            "note": None,
            "lines": [{"product_id": simple_product.id, "unit_target": "principale", "quantity": 5, "unit_cost": 1000}],
        },
    ).json()

    results = {}

    def _validate(barrier, index):
        with TestClient(app) as local_client:
            barrier.wait(timeout=5)
            results[index] = local_client.post(f"/stock-receipts/{receipt['id']}/validate", headers=auth_headers)

    barrier = threading.Barrier(2)
    threads = [threading.Thread(target=_validate, args=(barrier, i)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    statuses = sorted(r.status_code for r in results.values())
    assert statuses == [200, 400], statuses

    db_session.refresh(simple_product)
    assert simple_product.quantity == 15  # 10 + 5, crédité une seule fois

    movements = client.get("/stock-receipts/movements", headers=auth_headers).json()
    assert movements["total"] == 1


def test_concurrent_invoice_cancellation_only_one_succeeds(client, auth_headers, db_session, simple_product):
    invoice = client.post(
        "/invoices",
        headers=auth_headers,
        json={"lines": [{"product_id": simple_product.id, "quantity": 4}]},
    ).json()

    results = {}

    def _cancel(barrier, index):
        with TestClient(app) as local_client:
            barrier.wait(timeout=5)
            results[index] = local_client.post(
                f"/invoices/{invoice['id']}/cancel", headers=auth_headers, json={"reason": "essai concurrent"}
            )

    barrier = threading.Barrier(2)
    threads = [threading.Thread(target=_cancel, args=(barrier, i)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    statuses = sorted(r.status_code for r in results.values())
    assert statuses == [200, 400], statuses

    db_session.refresh(simple_product)
    assert simple_product.quantity == 10  # revenu à la valeur de départ, recrédité une seule fois
