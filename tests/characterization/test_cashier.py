"""Caractérise /caisse/* (module cashier) : résumé et journal du jour,
date invalide, paiement annulé exclu, client "comptant" par défaut.

Réf. app/modules/cashier/cashier_service.py — aucun test de caractérisation
n'existait pour ce routeur avant la migration ; ce fichier ferme ce trou.
"""
from datetime import datetime


def _create_invoice_and_pay(client, auth_headers, product_id, quantity, amount, client_id=None, client_name=None):
    payload = {"lines": [{"product_id": product_id, "quantity": quantity}]}
    if client_id is not None:
        payload["client_id"] = client_id
    if client_name is not None:
        payload["client_name"] = client_name
    invoice = client.post("/invoices", headers=auth_headers, json=payload).json()
    payment = client.post(f"/invoices/{invoice['id']}/payments", headers=auth_headers, json={"amount": amount}).json()
    return invoice, payment


def test_daily_summary_aggregates_invoices_and_payments(client, auth_headers, simple_product):
    _create_invoice_and_pay(client, auth_headers, simple_product.id, 2, 10000)

    resp = client.get("/caisse/summary", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == datetime.utcnow().strftime("%Y-%m-%d")
    assert body["invoices_count"] == 1
    assert body["total_invoiced"] == 2 * simple_product.unit_price
    assert body["total_collected"] == 10000
    assert body["remaining"] == body["total_invoiced"] - 10000


def test_daily_summary_invalid_date_returns_400(client, auth_headers):
    resp = client.get("/caisse/summary", headers=auth_headers, params={"date": "bad-date"})
    assert resp.status_code == 400
    assert "Date invalide" in resp.json()["detail"]


def test_daily_summary_excludes_voided_payments(client, auth_headers, simple_product):
    invoice, payment = _create_invoice_and_pay(client, auth_headers, simple_product.id, 1, 5000)
    client.post(
        f"/invoices/{invoice['id']}/payments/{payment['id']}/void",
        headers=auth_headers,
        json={"reason": "erreur"},
    )
    resp = client.get("/caisse/summary", headers=auth_headers)
    assert resp.json()["total_collected"] == 0


def test_daily_journal_lists_entries_with_client_comptant_fallback(client, auth_headers, simple_product):
    _create_invoice_and_pay(client, auth_headers, simple_product.id, 1, 5000)

    resp = client.get("/caisse/journal", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["client_name"] == "Client comptant"
    assert body["items"][0]["amount"] == 5000


def test_daily_journal_uses_client_name_when_provided(client, auth_headers, simple_product):
    _create_invoice_and_pay(client, auth_headers, simple_product.id, 1, 5000, client_name="Awa Ndiaye")

    resp = client.get("/caisse/journal", headers=auth_headers)
    assert resp.json()["items"][0]["client_name"] == "Awa Ndiaye"


def test_daily_journal_invalid_date_returns_400(client, auth_headers):
    resp = client.get("/caisse/journal", headers=auth_headers, params={"date": "nope"})
    assert resp.status_code == 400
