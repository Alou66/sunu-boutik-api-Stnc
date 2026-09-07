"""Caractérise /bons-clients (module bon_client) : CRUD, validation, recherche
dans le titre/le contenu/la date de création, isolation par boutique.
"""


def test_create_bon_client_success(client, auth_headers):
    resp = client.post("/bons-clients", headers=auth_headers, json={"title": "Rappel", "content": "Payer le fournisseur Mamadou"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Rappel"
    assert body["content"] == "Payer le fournisseur Mamadou"
    assert body["created_at"][:19] == body["updated_at"][:19]


def test_create_bon_client_empty_title_returns_400(client, auth_headers):
    resp = client.post("/bons-clients", headers=auth_headers, json={"title": "   ", "content": "Contenu"})
    assert resp.status_code == 400
    assert "titre" in resp.json()["detail"]


def test_create_bon_client_empty_content_returns_400(client, auth_headers):
    resp = client.post("/bons-clients", headers=auth_headers, json={"title": "Titre", "content": "   "})
    assert resp.status_code == 400
    assert "contenu" in resp.json()["detail"]


def test_list_bons_clients_search_by_title_or_content(client, auth_headers):
    client.post("/bons-clients", headers=auth_headers, json={"title": "Dette Mamadou", "content": "5000 FCFA"})
    client.post("/bons-clients", headers=auth_headers, json={"title": "Fournisseur", "content": "Contacter Mamadou pour la livraison"})
    client.post("/bons-clients", headers=auth_headers, json={"title": "Autre", "content": "Rien à voir"})

    by_title = client.get("/bons-clients", headers=auth_headers, params={"search": "Mamadou"})
    assert by_title.json()["total"] == 2

    by_content = client.get("/bons-clients", headers=auth_headers, params={"search": "livraison"})
    assert by_content.json()["total"] == 1
    assert by_content.json()["items"][0]["title"] == "Fournisseur"


def test_list_bons_clients_search_by_creation_date(client, auth_headers):
    created = client.post("/bons-clients", headers=auth_headers, json={"title": "Bon du jour", "content": "Contenu"}).json()
    created_date = created["created_at"][:10]  # YYYY-MM-DD

    resp = client.get("/bons-clients", headers=auth_headers, params={"search": created_date})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_get_bon_client_not_found_returns_404(client, auth_headers):
    resp = client.get("/bons-clients/999999", headers=auth_headers)
    assert resp.status_code == 404


def test_update_bon_client_partial_only_changes_given_field(client, auth_headers):
    created = client.post("/bons-clients", headers=auth_headers, json={"title": "Titre", "content": "Contenu"}).json()
    updated = client.patch(f"/bons-clients/{created['id']}", headers=auth_headers, json={"content": "Nouveau contenu"})
    assert updated.status_code == 200
    body = updated.json()
    assert body["title"] == "Titre"
    assert body["content"] == "Nouveau contenu"


def test_update_bon_client_empty_title_returns_400(client, auth_headers):
    created = client.post("/bons-clients", headers=auth_headers, json={"title": "Titre", "content": "Contenu"}).json()
    resp = client.patch(f"/bons-clients/{created['id']}", headers=auth_headers, json={"title": "   "})
    assert resp.status_code == 400


def test_update_bon_client_not_found_returns_404(client, auth_headers):
    resp = client.patch("/bons-clients/999999", headers=auth_headers, json={"title": "Titre"})
    assert resp.status_code == 404


def test_delete_bon_client_succeeds(client, auth_headers):
    created = client.post("/bons-clients", headers=auth_headers, json={"title": "Titre", "content": "Contenu"}).json()
    resp = client.delete(f"/bons-clients/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204
    assert client.get(f"/bons-clients/{created['id']}", headers=auth_headers).status_code == 404


def test_delete_bon_client_not_found_returns_404(client, auth_headers):
    resp = client.delete("/bons-clients/999999", headers=auth_headers)
    assert resp.status_code == 404


def test_bons_clients_are_isolated_per_shop(client, auth_headers, db_session):
    from app.core.security import create_access_token, hash_password
    from app.modules.identity.identity_model import Shop, ShopStatus, User, UserRole

    other_shop = Shop(name="Autre Boutique", status=ShopStatus.APPROVED)
    db_session.add(other_shop)
    db_session.commit()
    db_session.refresh(other_shop)

    other_owner = User(
        shop_id=other_shop.id,
        full_name="Autre Propriétaire",
        email="other-owner@example.com",
        hashed_password=hash_password("Test1234!"),
        role=UserRole.OWNER,
        is_active=True,
    )
    db_session.add(other_owner)
    db_session.commit()
    db_session.refresh(other_owner)
    other_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(other_owner.id)})}"}

    created = client.post("/bons-clients", headers=auth_headers, json={"title": "Titre", "content": "Contenu"}).json()

    resp = client.get(f"/bons-clients/{created['id']}", headers=other_headers)
    assert resp.status_code == 404

    other_list = client.get("/bons-clients", headers=other_headers)
    assert other_list.json()["total"] == 0
