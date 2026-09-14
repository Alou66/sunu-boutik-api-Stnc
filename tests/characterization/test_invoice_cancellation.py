"""Caractérise l'annulation et la suppression de facture : recrédit du stock,
blocage si un paiement a été reçu, suppression réservée aux factures annulées,
et non-régression de la numérotation après suppression (voir
InvoiceRepository.next_sequence_for_shop).

Réf. app/modules/billing/billing_service.py::InvoiceService.cancel/delete.
"""
import re


def test_cancel_invoice_restocks_simple_product(client, auth_headers, simple_product):
    create_resp = client.post(
        "/invoices",
        headers=auth_headers,
        json={"lines": [{"product_id": simple_product.id, "quantity": 3}]},
    )
    invoice_id = create_resp.json()["id"]
    assert client.get(f"/products/{simple_product.id}", headers=auth_headers).json()["quantity"] == 7

    cancel_resp = client.post(
        f"/invoices/{invoice_id}/cancel", headers=auth_headers, json={"reason": "Erreur de saisie"}
    )
    assert cancel_resp.status_code == 200
    body = cancel_resp.json()
    assert body["status"] == "cancelled"
    assert body["cancel_reason"] == "Erreur de saisie"
    assert body["cancelled_at"] is not None

    assert client.get(f"/products/{simple_product.id}", headers=auth_headers).json()["quantity"] == 10


def test_cancel_invoice_restocks_transformable_product_both_forms(client, auth_headers, db_session, transformable_product):
    transformable_product.quantity_secondaire = 5
    db_session.commit()

    create_resp = client.post(
        "/invoices",
        headers=auth_headers,
        json={
            "lines": [
                {"product_id": transformable_product.id, "quantity": 1, "form": "principale"},
                {"product_id": transformable_product.id, "quantity": 2, "form": "secondaire"},
            ]
        },
    )
    invoice_id = create_resp.json()["id"]
    stock = client.get(f"/products/{transformable_product.id}", headers=auth_headers).json()
    assert stock["quantity"] == 2
    assert stock["quantity_secondaire"] == 3

    cancel_resp = client.post(f"/invoices/{invoice_id}/cancel", headers=auth_headers, json={"reason": "Test"})
    assert cancel_resp.status_code == 200

    stock = client.get(f"/products/{transformable_product.id}", headers=auth_headers).json()
    assert stock["quantity"] == 3
    assert stock["quantity_secondaire"] == 5


def test_cancel_invoice_requires_reason(client, auth_headers, simple_product):
    create_resp = client.post(
        "/invoices", headers=auth_headers, json={"lines": [{"product_id": simple_product.id, "quantity": 1}]}
    )
    invoice_id = create_resp.json()["id"]

    resp = client.post(f"/invoices/{invoice_id}/cancel", headers=auth_headers, json={"reason": "  "})
    assert resp.status_code == 422


def test_cancel_invoice_blocked_once_payment_received(client, auth_headers, simple_product):
    create_resp = client.post(
        "/invoices", headers=auth_headers, json={"lines": [{"product_id": simple_product.id, "quantity": 1}]}
    )
    invoice_id = create_resp.json()["id"]
    client.post(f"/invoices/{invoice_id}/payments", headers=auth_headers, json={"amount": 1000})

    resp = client.post(f"/invoices/{invoice_id}/cancel", headers=auth_headers, json={"reason": "Test"})
    assert resp.status_code == 400
    assert "déjà reçu un paiement" in resp.json()["detail"]

    # Le stock ne doit pas avoir été recrédité puisque l'annulation a été refusée.
    assert client.get(f"/products/{simple_product.id}", headers=auth_headers).json()["quantity"] == 9


def test_cancel_invoice_twice_returns_400(client, auth_headers, simple_product):
    create_resp = client.post(
        "/invoices", headers=auth_headers, json={"lines": [{"product_id": simple_product.id, "quantity": 1}]}
    )
    invoice_id = create_resp.json()["id"]
    client.post(f"/invoices/{invoice_id}/cancel", headers=auth_headers, json={"reason": "Test"})

    resp = client.post(f"/invoices/{invoice_id}/cancel", headers=auth_headers, json={"reason": "Test 2"})
    assert resp.status_code == 400
    assert "déjà annulée" in resp.json()["detail"]


def test_update_invoice_blocked_once_cancelled(client, auth_headers, simple_product):
    create_resp = client.post(
        "/invoices", headers=auth_headers, json={"lines": [{"product_id": simple_product.id, "quantity": 1}]}
    )
    invoice_id = create_resp.json()["id"]
    client.post(f"/invoices/{invoice_id}/cancel", headers=auth_headers, json={"reason": "Test"})

    resp = client.patch(
        f"/invoices/{invoice_id}",
        headers=auth_headers,
        json={"lines": [{"product_id": simple_product.id, "quantity": 2}]},
    )
    assert resp.status_code == 400
    assert "annulée" in resp.json()["detail"]


def test_delete_invoice_blocked_when_not_cancelled(client, auth_headers, simple_product):
    create_resp = client.post(
        "/invoices", headers=auth_headers, json={"lines": [{"product_id": simple_product.id, "quantity": 1}]}
    )
    invoice_id = create_resp.json()["id"]

    resp = client.delete(f"/invoices/{invoice_id}", headers=auth_headers)
    assert resp.status_code == 400
    assert "Seule une facture annulée" in resp.json()["detail"]


def test_delete_cancelled_invoice_succeeds_and_is_gone(client, auth_headers, simple_product):
    create_resp = client.post(
        "/invoices", headers=auth_headers, json={"lines": [{"product_id": simple_product.id, "quantity": 1}]}
    )
    invoice_id = create_resp.json()["id"]
    client.post(f"/invoices/{invoice_id}/cancel", headers=auth_headers, json={"reason": "Test"})

    resp = client.delete(f"/invoices/{invoice_id}", headers=auth_headers)
    assert resp.status_code == 204

    assert client.get(f"/invoices/{invoice_id}", headers=auth_headers).status_code == 404


def test_deleting_cancelled_invoice_does_not_create_numbering_collision(client, auth_headers, simple_product):
    """Régression : la numérotation basée sur COUNT(*) redescendait après une
    suppression et pouvait régénérer un numéro déjà pris par une facture plus
    récente encore existante, bloquant toute création future (voir
    InvoiceRepository.next_sequence_for_shop). Ce test crée A, B, annule et
    supprime A (le plus ancien, pas le plus récent), puis vérifie qu'une
    nouvelle facture C peut toujours être créée avec un numéro distinct de B.
    """
    resp_a = client.post(
        "/invoices", headers=auth_headers, json={"lines": [{"product_id": simple_product.id, "quantity": 1}]}
    )
    invoice_a = resp_a.json()
    resp_b = client.post(
        "/invoices", headers=auth_headers, json={"lines": [{"product_id": simple_product.id, "quantity": 1}]}
    )
    invoice_b = resp_b.json()
    assert invoice_a["number"] != invoice_b["number"]

    client.post(f"/invoices/{invoice_a['id']}/cancel", headers=auth_headers, json={"reason": "Test"})
    del_resp = client.delete(f"/invoices/{invoice_a['id']}", headers=auth_headers)
    assert del_resp.status_code == 204

    resp_c = client.post(
        "/invoices", headers=auth_headers, json={"lines": [{"product_id": simple_product.id, "quantity": 1}]}
    )
    assert resp_c.status_code == 201
    invoice_c = resp_c.json()
    assert re.fullmatch(r"FA\d{8}-\d{4}", invoice_c["number"])
    assert invoice_c["number"] != invoice_b["number"]


def test_cancelled_invoice_excluded_from_cashier_daily_summary(client, auth_headers, simple_product):
    create_resp = client.post(
        "/invoices", headers=auth_headers, json={"lines": [{"product_id": simple_product.id, "quantity": 1}]}
    )
    invoice = create_resp.json()

    before = client.get("/caisse/summary", headers=auth_headers).json()
    assert before["total_invoiced"] == invoice["total"]

    client.post(f"/invoices/{invoice['id']}/cancel", headers=auth_headers, json={"reason": "Test"})

    after = client.get("/caisse/summary", headers=auth_headers).json()
    assert after["total_invoiced"] == before["total_invoiced"] - invoice["total"]


def test_list_invoices_status_filter_cancelled(client, auth_headers, simple_product):
    create_resp = client.post(
        "/invoices", headers=auth_headers, json={"lines": [{"product_id": simple_product.id, "quantity": 1}]}
    )
    invoice_id = create_resp.json()["id"]
    client.post(f"/invoices/{invoice_id}/cancel", headers=auth_headers, json={"reason": "Test"})

    resp = client.get("/invoices?status_filter=cancelled", headers=auth_headers)
    assert resp.status_code == 200
    ids = [inv["id"] for inv in resp.json()["items"]]
    assert invoice_id in ids

    unpaid_resp = client.get("/invoices?status_filter=unpaid", headers=auth_headers)
    unpaid_ids = [inv["id"] for inv in unpaid_resp.json()["items"]]
    assert invoice_id not in unpaid_ids
