"""Caractérise le verrouillage transactionnel (FOR UPDATE) qui protège contre
la survente en cas de deux créations de facture simultanées sur le même
article. Réf. app/routers/invoices.py::_apply_lines (verrou posé par ligne
produit) et _lock_shop_for_numbering (verrou posé sur la boutique).
"""
import threading

from fastapi.testclient import TestClient

from app.main import app


def _post_invoice(results, index, headers, product_id, quantity, barrier):
    with TestClient(app) as local_client:
        barrier.wait(timeout=5)
        resp = local_client.post(
            "/invoices",
            headers=headers,
            json={"lines": [{"product_id": product_id, "quantity": quantity}]},
        )
        results[index] = resp


def test_concurrent_invoice_creation_never_oversells(client, auth_headers, db_session, simple_product):
    simple_product.quantity = 1
    db_session.commit()

    results = {}
    barrier = threading.Barrier(2)
    threads = [
        threading.Thread(target=_post_invoice, args=(results, i, auth_headers, simple_product.id, 1, barrier))
        for i in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    statuses = sorted(r.status_code for r in results.values())
    assert statuses == [201, 400], statuses

    failed = next(r for r in results.values() if r.status_code == 400)
    assert "Stock insuffisant" in failed.json()["detail"]

    final_stock = client.get(f"/products/{simple_product.id}", headers=auth_headers).json()
    assert final_stock["quantity"] == 0


def test_concurrent_invoice_creation_assigns_distinct_numbers(client, auth_headers, db_session, category, shop):
    from app.modules.products.products_model import Product

    product = Product(shop_id=shop.id, category_id=category.id, name="Sucre 1kg", unit_price=700, quantity=100)
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    results = {}
    barrier = threading.Barrier(2)
    threads = [
        threading.Thread(target=_post_invoice, args=(results, i, auth_headers, product.id, 1, barrier))
        for i in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    numbers = {r.json()["number"] for r in results.values() if r.status_code == 201}
    assert len(numbers) == 2, "les deux factures doivent avoir des numéros distincts, sans doublon"
