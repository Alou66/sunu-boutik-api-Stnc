"""Caractérise le comportement actuel de la création/modification de facture :
décrément de stock (article simple et transformable), étiquetage des lignes,
et blocage de la modification une fois un paiement reçu.

Réf. app/routers/invoices.py::_apply_lines, create_invoice, update_invoice.
"""
import re


def test_create_invoice_decrements_simple_product_stock(client, auth_headers, simple_product):
    resp = client.post(
        "/invoices",
        headers=auth_headers,
        json={"lines": [{"product_id": simple_product.id, "quantity": 3}]},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["total"] == 3 * simple_product.unit_price
    assert body["status"] == "unpaid"
    assert body["balance_due"] == body["total"]
    assert body["lines"][0]["product_name"] == simple_product.name

    stock_resp = client.get(f"/products/{simple_product.id}", headers=auth_headers)
    assert stock_resp.json()["quantity"] == 7


def test_create_invoice_transformable_product_principale_form(client, auth_headers, transformable_product):
    resp = client.post(
        "/invoices",
        headers=auth_headers,
        json={"lines": [{"product_id": transformable_product.id, "quantity": 1, "form": "principale"}]},
    )
    assert resp.status_code == 201
    line = resp.json()["lines"][0]
    assert line["product_name"] == f"CARTON {transformable_product.name}"
    assert line["unit_price"] == transformable_product.unit_price

    stock = client.get(f"/products/{transformable_product.id}", headers=auth_headers).json()
    assert stock["quantity"] == 2
    assert stock["quantity_secondaire"] == 0


def test_create_invoice_transformable_product_secondaire_form(client, auth_headers, db_session, transformable_product):
    transformable_product.quantity_secondaire = 5
    db_session.commit()

    resp = client.post(
        "/invoices",
        headers=auth_headers,
        json={"lines": [{"product_id": transformable_product.id, "quantity": 2, "form": "secondaire"}]},
    )
    assert resp.status_code == 201
    line = resp.json()["lines"][0]
    assert line["product_name"] == f"SEAU {transformable_product.name}"
    assert line["unit_price"] == transformable_product.unit_price_secondaire
    assert line["line_total"] == 2 * transformable_product.unit_price_secondaire

    stock = client.get(f"/products/{transformable_product.id}", headers=auth_headers).json()
    assert stock["quantity"] == 3
    assert stock["quantity_secondaire"] == 3


def test_create_invoice_insufficient_stock_returns_400_and_does_not_decrement(client, auth_headers, simple_product):
    resp = client.post(
        "/invoices",
        headers=auth_headers,
        json={"lines": [{"product_id": simple_product.id, "quantity": 999}]},
    )
    assert resp.status_code == 400
    assert "Stock insuffisant" in resp.json()["detail"]

    stock = client.get(f"/products/{simple_product.id}", headers=auth_headers).json()
    assert stock["quantity"] == 10


def test_create_invoice_idempotency_key_replayed_returns_same_invoice(client, auth_headers, simple_product):
    payload = {"lines": [{"product_id": simple_product.id, "quantity": 3}], "idempotency_key": "retry-key-invoice-1"}

    first = client.post("/invoices", headers=auth_headers, json=payload)
    second = client.post("/invoices", headers=auth_headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    stock = client.get(f"/products/{simple_product.id}", headers=auth_headers).json()
    assert stock["quantity"] == 7  # décrémenté une seule fois malgré les deux requêtes

    invoices = client.get("/invoices", headers=auth_headers).json()
    assert invoices["total"] == 1


def test_invoice_number_format(client, auth_headers, simple_product):
    resp = client.post(
        "/invoices",
        headers=auth_headers,
        json={"lines": [{"product_id": simple_product.id, "quantity": 1}]},
    )
    number = resp.json()["number"]
    assert re.fullmatch(r"FA\d{8}-\d{4}", number), number


def test_update_invoice_reverts_old_lines_and_reapplies_new(client, auth_headers, db_session, simple_product, category, shop):
    from app.modules.products.products_model import Product

    other = Product(shop_id=shop.id, category_id=category.id, name="Huile 1L", unit_price=1200, quantity=20)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    create_resp = client.post(
        "/invoices",
        headers=auth_headers,
        json={"lines": [{"product_id": simple_product.id, "quantity": 4}]},
    )
    invoice_id = create_resp.json()["id"]
    assert client.get(f"/products/{simple_product.id}", headers=auth_headers).json()["quantity"] == 6

    update_resp = client.patch(
        f"/invoices/{invoice_id}",
        headers=auth_headers,
        json={"lines": [{"product_id": other.id, "quantity": 2}]},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["total"] == 2 * other.unit_price

    # L'ancienne ligne (simple_product) doit avoir été créditée intégralement.
    assert client.get(f"/products/{simple_product.id}", headers=auth_headers).json()["quantity"] == 10
    assert client.get(f"/products/{other.id}", headers=auth_headers).json()["quantity"] == 18


def test_update_invoice_blocked_once_payment_received(client, auth_headers, simple_product):
    create_resp = client.post(
        "/invoices",
        headers=auth_headers,
        json={"lines": [{"product_id": simple_product.id, "quantity": 1}]},
    )
    invoice_id = create_resp.json()["id"]
    client.post(f"/invoices/{invoice_id}/payments", headers=auth_headers, json={"amount": 1000})

    update_resp = client.patch(
        f"/invoices/{invoice_id}",
        headers=auth_headers,
        json={"lines": [{"product_id": simple_product.id, "quantity": 2}]},
    )
    assert update_resp.status_code == 400
    assert "déjà reçu un paiement" in update_resp.json()["detail"]
