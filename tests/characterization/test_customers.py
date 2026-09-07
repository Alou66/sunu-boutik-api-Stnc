"""Caractérise /clients (module customers) : doublon téléphone/nom, validation
du format de téléphone, mise à jour partielle, suppression bloquée par facture.

Réf. app/modules/customers/customers_service.py — aucun test de caractérisation
n'existait pour ce routeur avant la migration ; ce fichier ferme ce trou.
"""


def test_create_client_success(client, auth_headers):
    resp = client.post("/clients", headers=auth_headers, json={"name": "Jean Diop", "phone": "771234567", "address": "Dakar"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Jean Diop"
    assert body["phone"] == "771234567"


def test_create_client_duplicate_phone_returns_409(client, auth_headers):
    client.post("/clients", headers=auth_headers, json={"name": "Jean Diop", "phone": "771234567"})
    resp = client.post("/clients", headers=auth_headers, json={"name": "Autre Nom", "phone": "771234567"})
    assert resp.status_code == 409
    assert "numéro de téléphone" in resp.json()["detail"]


def test_create_client_duplicate_name_case_insensitive_returns_409(client, auth_headers):
    client.post("/clients", headers=auth_headers, json={"name": "Jean Diop"})
    resp = client.post("/clients", headers=auth_headers, json={"name": "jean diop"})
    assert resp.status_code == 409
    assert "nom" in resp.json()["detail"]


def test_create_client_invalid_phone_format_returns_422(client, auth_headers):
    resp = client.post("/clients", headers=auth_headers, json={"name": "Test", "phone": "123"})
    assert resp.status_code == 422


def test_create_client_empty_name_returns_400(client, auth_headers):
    resp = client.post("/clients", headers=auth_headers, json={"name": "   "})
    assert resp.status_code == 400


def test_list_clients_search_by_name_or_phone(client, auth_headers):
    client.post("/clients", headers=auth_headers, json={"name": "Awa Ndiaye", "phone": "770001111"})
    client.post("/clients", headers=auth_headers, json={"name": "Moussa Fall", "phone": "770002222"})

    by_name = client.get("/clients", headers=auth_headers, params={"search": "Awa"})
    assert by_name.json()["total"] == 1

    by_phone = client.get("/clients", headers=auth_headers, params={"search": "770002222"})
    assert by_phone.json()["total"] == 1
    assert by_phone.json()["items"][0]["name"] == "Moussa Fall"


def test_update_client_partial_only_changes_given_field(client, auth_headers):
    created = client.post("/clients", headers=auth_headers, json={"name": "Jean Diop", "phone": "771234567"}).json()
    updated = client.patch(f"/clients/{created['id']}", headers=auth_headers, json={"address": "Pikine"})
    assert updated.status_code == 200
    body = updated.json()
    assert body["address"] == "Pikine"
    assert body["name"] == "Jean Diop"
    assert body["phone"] == "771234567"


def test_get_client_not_found_returns_404(client, auth_headers):
    resp = client.get("/clients/999999", headers=auth_headers)
    assert resp.status_code == 404


def test_delete_client_used_in_invoice_returns_409(client, auth_headers, simple_product):
    created = client.post("/clients", headers=auth_headers, json={"name": "Jean Diop"}).json()
    client.post(
        "/invoices",
        headers=auth_headers,
        json={"client_id": created["id"], "lines": [{"product_id": simple_product.id, "quantity": 1}]},
    )
    resp = client.delete(f"/clients/{created['id']}", headers=auth_headers)
    assert resp.status_code == 409
    assert "facture" in resp.json()["detail"]


def test_delete_client_without_invoice_succeeds(client, auth_headers):
    created = client.post("/clients", headers=auth_headers, json={"name": "Jean Diop"}).json()
    resp = client.delete(f"/clients/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204
    assert client.get(f"/clients/{created['id']}", headers=auth_headers).status_code == 404
