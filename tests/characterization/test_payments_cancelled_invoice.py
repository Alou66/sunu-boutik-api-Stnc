"""Caractérise le refus d'un paiement sur une facture annulée (étape 0.1.3).

Réf. app/modules/payments/payments_service.py::PaymentService.create : une
facture annulée (InvoiceService.cancel) ne peut plus recevoir de paiement, même
si elle n'a jamais été payée (balance_due == total > 0).
"""
from app.modules.payments.payments_model import Payment


def _create_invoice(client, auth_headers, product_id, quantity=1):
    resp = client.post(
        "/invoices",
        headers=auth_headers,
        json={"lines": [{"product_id": product_id, "quantity": quantity}]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _cancel(client, auth_headers, invoice_id):
    resp = client.post(f"/invoices/{invoice_id}/cancel", headers=auth_headers, json={"reason": "Erreur de saisie"})
    assert resp.status_code == 200, resp.text


def test_payment_on_cancelled_invoice_returns_400_and_creates_no_payment(
    client, auth_headers, db_session, simple_product
):
    invoice = _create_invoice(client, auth_headers, simple_product.id)
    _cancel(client, auth_headers, invoice["id"])

    resp = client.post(f"/invoices/{invoice['id']}/payments", headers=auth_headers, json={"amount": 5000})

    assert resp.status_code == 400
    assert "annulée" in resp.json()["detail"]
    assert db_session.query(Payment).filter(Payment.invoice_id == invoice["id"]).count() == 0

    after = client.get(f"/invoices/{invoice['id']}", headers=auth_headers).json()
    assert after["status"] == "cancelled"
    assert after["amount_paid"] == 0
    assert client.get(f"/invoices/{invoice['id']}/payments", headers=auth_headers).json() == []


def test_payment_with_idempotency_key_on_cancelled_invoice_is_refused_too(
    client, auth_headers, db_session, simple_product
):
    invoice = _create_invoice(client, auth_headers, simple_product.id)
    _cancel(client, auth_headers, invoice["id"])

    payload = {"amount": invoice["total"], "idempotency_key": "cle-facture-annulee"}
    resp = client.post(f"/invoices/{invoice['id']}/payments", headers=auth_headers, json=payload)

    assert resp.status_code == 400
    assert db_session.query(Payment).count() == 0


def test_payment_on_active_invoice_is_still_accepted(client, auth_headers, db_session, simple_product):
    invoice = _create_invoice(client, auth_headers, simple_product.id)

    resp = client.post(f"/invoices/{invoice['id']}/payments", headers=auth_headers, json={"amount": 5000})

    assert resp.status_code == 201
    assert resp.json()["amount"] == 5000
    assert db_session.query(Payment).filter(Payment.invoice_id == invoice["id"]).count() == 1
    updated = client.get(f"/invoices/{invoice['id']}", headers=auth_headers).json()
    assert updated["status"] == "partial"
    assert updated["amount_paid"] == 5000


def test_payment_on_other_shops_invoice_is_still_404(client, auth_headers):
    resp = client.post("/invoices/999999/payments", headers=auth_headers, json={"amount": 100})
    assert resp.status_code == 404
