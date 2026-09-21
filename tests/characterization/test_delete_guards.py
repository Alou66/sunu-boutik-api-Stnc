"""Caractérise les garde-fous de suppression (étapes 0.1.5 et 0.1.6) : supprimer
un article ou un employé encore référencé par des données historiques doit
renvoyer une erreur métier (400), jamais une violation de clé étrangère (500),
et ne doit rien supprimer d'autre au passage (historique de stock, réceptions,
factures).

Réf. app/modules/products/products_service.py::ProductService.delete et
app/modules/employees/employees_repository.py::has_related_records.
"""
from app.modules.billing.billing_model import Invoice, InvoiceLine
from app.modules.identity.identity_model import User
from app.modules.products.products_model import Product
from app.modules.stock_receipts.stock_receipts_model import StockMovement, StockReceipt, StockReceiptLine


def _history_counts(db_session):
    db_session.expire_all()
    return {
        "receipts": db_session.query(StockReceipt).count(),
        "receipt_lines": db_session.query(StockReceiptLine).count(),
        "movements": db_session.query(StockMovement).count(),
        "invoices": db_session.query(Invoice).count(),
        "invoice_lines": db_session.query(InvoiceLine).count(),
    }


# ---- 0.1.5 : suppression d'article ----


def test_delete_product_without_dependencies_is_still_allowed(client, auth_headers, db_session, simple_product):
    resp = client.delete(f"/products/{simple_product.id}", headers=auth_headers)

    assert resp.status_code == 204
    assert db_session.query(Product).filter(Product.id == simple_product.id).count() == 0


def test_delete_product_referenced_by_stock_receipt_line_returns_400(
    client, auth_headers, db_session, shop, simple_product
):
    created = client.post(
        "/stock-receipts",
        headers=auth_headers,
        json={
            "supplier_id": None,
            "reference": "BL-001",
            "note": None,
            "lines": [{"product_id": simple_product.id, "unit_target": "principale", "quantity": 5, "unit_cost": 1000}],
        },
    )
    assert created.status_code == 201, created.text
    before = _history_counts(db_session)
    assert before["receipt_lines"] == 1

    resp = client.delete(f"/products/{simple_product.id}", headers=auth_headers)

    assert resp.status_code == 400
    assert "réceptions de stock" in resp.json()["detail"]
    assert _history_counts(db_session) == before
    assert db_session.query(Product).filter(Product.id == simple_product.id).count() == 1


def test_delete_product_referenced_by_stock_movement_returns_400(
    client, auth_headers, db_session, shop, owner, simple_product
):
    # Mouvement isolé (sans ligne de réception) : seule la FK stock_movements.product_id
    # retient l'article.
    db_session.add(
        StockMovement(
            shop_id=shop.id,
            product_id=simple_product.id,
            product_name=simple_product.name,
            source_type="receipt",
            source_id=1,
            unit_target="principale",
            quantity_delta=5,
            created_by_id=owner.id,
        )
    )
    db_session.commit()
    before = _history_counts(db_session)
    assert before["movements"] == 1 and before["receipt_lines"] == 0

    resp = client.delete(f"/products/{simple_product.id}", headers=auth_headers)

    assert resp.status_code == 400
    assert "mouvements de stock" in resp.json()["detail"]
    assert _history_counts(db_session) == before
    assert db_session.query(Product).filter(Product.id == simple_product.id).count() == 1


def test_delete_product_after_validated_receipt_keeps_whole_history(client, auth_headers, db_session, simple_product):
    created = client.post(
        "/stock-receipts",
        headers=auth_headers,
        json={
            "supplier_id": None,
            "reference": None,
            "note": None,
            "lines": [{"product_id": simple_product.id, "unit_target": "principale", "quantity": 5, "unit_cost": 1000}],
        },
    ).json()
    assert client.post(f"/stock-receipts/{created['id']}/validate", headers=auth_headers).status_code == 200
    before = _history_counts(db_session)
    assert before["receipt_lines"] == 1 and before["movements"] == 1

    resp = client.delete(f"/products/{simple_product.id}", headers=auth_headers)

    assert resp.status_code == 400
    assert _history_counts(db_session) == before
    db_session.refresh(simple_product)
    assert simple_product.quantity == 15


def test_delete_product_referenced_by_invoice_still_returns_400(client, auth_headers, db_session, simple_product):
    client.post("/invoices", headers=auth_headers, json={"lines": [{"product_id": simple_product.id, "quantity": 1}]})

    resp = client.delete(f"/products/{simple_product.id}", headers=auth_headers)

    assert resp.status_code == 400
    assert "factures" in resp.json()["detail"]


# ---- 0.1.6 : suppression d'employé ----


def test_delete_employee_without_history_is_still_allowed(client, auth_headers, db_session, employee):
    resp = client.delete(f"/employees/{employee.id}", headers=auth_headers)

    assert resp.status_code == 204
    assert db_session.query(User).filter(User.id == employee.id).count() == 0


def test_delete_employee_who_created_an_invoice_returns_400(
    client, auth_headers, employee_headers, db_session, employee, simple_product
):
    created = client.post(
        "/invoices", headers=employee_headers, json={"lines": [{"product_id": simple_product.id, "quantity": 1}]}
    )
    assert created.status_code == 201, created.text
    invoice_id = created.json()["id"]
    users_before = db_session.query(User).count()
    before = _history_counts(db_session)

    resp = client.delete(f"/employees/{employee.id}", headers=auth_headers)

    assert resp.status_code == 400
    assert "opérations associées" in resp.json()["detail"]
    assert db_session.query(User).count() == users_before
    assert _history_counts(db_session) == before
    db_session.expire_all()
    invoice = db_session.query(Invoice).filter(Invoice.id == invoice_id).one()
    assert invoice.created_by_id == employee.id
    assert invoice.cancelled_by_id is None


def test_delete_employee_who_cancelled_an_invoice_returns_400(
    client, auth_headers, employee_headers, db_session, owner, employee, simple_product
):
    # Facture créée par le propriétaire, annulée par l'employé : l'employé n'est
    # référencé QUE par invoices.cancelled_by_id.
    created = client.post(
        "/invoices", headers=auth_headers, json={"lines": [{"product_id": simple_product.id, "quantity": 1}]}
    )
    assert created.status_code == 201, created.text
    invoice_id = created.json()["id"]
    cancelled = client.post(
        f"/invoices/{invoice_id}/cancel", headers=employee_headers, json={"reason": "Erreur de caisse"}
    )
    assert cancelled.status_code == 200, cancelled.text
    users_before = db_session.query(User).count()
    before = _history_counts(db_session)

    resp = client.delete(f"/employees/{employee.id}", headers=auth_headers)

    assert resp.status_code == 400
    assert "opérations associées" in resp.json()["detail"]
    assert db_session.query(User).count() == users_before
    assert _history_counts(db_session) == before
    db_session.expire_all()
    invoice = db_session.query(Invoice).filter(Invoice.id == invoice_id).one()
    assert invoice.created_by_id == owner.id
    assert invoice.cancelled_by_id == employee.id
