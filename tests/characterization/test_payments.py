"""Caractérise l'encaissement (idempotence, plafond du solde) et l'annulation
de paiement. Réf. app/routers/payments.py.
"""


def _create_invoice(client, auth_headers, product_id, quantity=1):
    resp = client.post(
        "/invoices",
        headers=auth_headers,
        json={"lines": [{"product_id": product_id, "quantity": quantity}]},
    )
    return resp.json()


def test_payment_with_idempotency_key_replayed_returns_same_payment(client, auth_headers, simple_product):
    invoice = _create_invoice(client, auth_headers, simple_product.id)
    payload = {"amount": 5000, "idempotency_key": "retry-key-1"}

    first = client.post(f"/invoices/{invoice['id']}/payments", headers=auth_headers, json=payload)
    second = client.post(f"/invoices/{invoice['id']}/payments", headers=auth_headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    updated_invoice = client.get(f"/invoices/{invoice['id']}", headers=auth_headers).json()
    assert updated_invoice["amount_paid"] == 5000
    assert updated_invoice["status"] == "partial"


def test_payment_rejects_amount_exceeding_balance_due(client, auth_headers, simple_product):
    invoice = _create_invoice(client, auth_headers, simple_product.id)
    resp = client.post(
        f"/invoices/{invoice['id']}/payments",
        headers=auth_headers,
        json={"amount": invoice["total"] + 1},
    )
    assert resp.status_code == 400
    assert "dépasse le solde restant" in resp.json()["detail"]


def test_payment_full_amount_marks_invoice_paid(client, auth_headers, simple_product):
    invoice = _create_invoice(client, auth_headers, simple_product.id)
    client.post(f"/invoices/{invoice['id']}/payments", headers=auth_headers, json={"amount": invoice["total"]})

    updated = client.get(f"/invoices/{invoice['id']}", headers=auth_headers).json()
    assert updated["status"] == "paid"
    assert updated["balance_due"] == 0


def test_void_payment_recomputes_amount_paid(client, auth_headers, simple_product):
    invoice = _create_invoice(client, auth_headers, simple_product.id)
    payment = client.post(
        f"/invoices/{invoice['id']}/payments", headers=auth_headers, json={"amount": 5000}
    ).json()

    void_resp = client.post(
        f"/invoices/{invoice['id']}/payments/{payment['id']}/void",
        headers=auth_headers,
        json={"reason": "erreur de saisie"},
    )
    assert void_resp.status_code == 200
    assert void_resp.json()["is_voided"] is True

    updated_invoice = client.get(f"/invoices/{invoice['id']}", headers=auth_headers).json()
    assert updated_invoice["amount_paid"] == 0
    assert updated_invoice["status"] == "unpaid"


def test_void_payment_twice_returns_400(client, auth_headers, simple_product):
    invoice = _create_invoice(client, auth_headers, simple_product.id)
    payment = client.post(
        f"/invoices/{invoice['id']}/payments", headers=auth_headers, json={"amount": 5000}
    ).json()
    client.post(
        f"/invoices/{invoice['id']}/payments/{payment['id']}/void",
        headers=auth_headers,
        json={"reason": "première annulation"},
    )
    second_void = client.post(
        f"/invoices/{invoice['id']}/payments/{payment['id']}/void",
        headers=auth_headers,
        json={"reason": "deuxième annulation"},
    )
    assert second_void.status_code == 400
    assert "déjà annulé" in second_void.json()["detail"]
