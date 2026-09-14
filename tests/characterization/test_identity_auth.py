"""Caractérise /auth/* (module identity) : inscription (avec et sans logo),
connexion selon le statut de la boutique, /me, changement de mot de passe,
mise à jour boutique, mot de passe oublié.

Réf. app/modules/identity/identity_service.py — aucun test de caractérisation
n'existait pour ce routeur avant la migration ; ce fichier ferme ce trou,
y compris le chemin d'upload de logo jamais exercé, même manuellement,
pendant la migration.
"""
import glob
import os

from app.core.security import hash_password
from app.modules.identity.identity_model import Shop, ShopStatus, User


def test_register_without_logo_creates_pending_shop_and_inactive_user(client, db_session):
    resp = client.post(
        "/auth/register",
        data={"shop_name": "Boutique Test", "full_name": "Awa Ndiaye", "email": "awa@example.com"},
    )
    assert resp.status_code == 201

    user = db_session.query(User).filter(User.email == "awa@example.com").first()
    shop = db_session.query(Shop).filter(Shop.id == user.shop_id).first()
    assert shop.status == ShopStatus.PENDING
    assert user.is_active is False
    assert user.hashed_password is None


def test_register_with_logo_saves_file(client, db_session):
    resp = client.post(
        "/auth/register",
        data={"shop_name": "Boutique Logo", "full_name": "Test Logo", "email": "logo@example.com"},
        files={"logo": ("logo.png", b"\x89PNG\r\n\x1a\nfake-bytes", "image/png")},
    )
    assert resp.status_code == 201

    user = db_session.query(User).filter(User.email == "logo@example.com").first()
    shop = db_session.query(Shop).filter(Shop.id == user.shop_id).first()
    assert shop.logo_path is not None
    assert os.path.exists(shop.logo_path)
    os.remove(shop.logo_path)  # nettoyage — uploads/ est gitignored mais autant ne pas laisser traîner


def test_register_with_invalid_logo_content_type_returns_400(client):
    resp = client.post(
        "/auth/register",
        data={"shop_name": "Boutique Bad Logo", "full_name": "Test", "email": "badlogo@example.com"},
        files={"logo": ("logo.txt", b"not-an-image", "text/plain")},
    )
    assert resp.status_code == 400
    assert "image" in resp.json()["detail"]
    for f in glob.glob("uploads/logos/*badlogo*"):
        os.remove(f)


def test_register_duplicate_email_returns_400(client):
    client.post("/auth/register", data={"shop_name": "A", "full_name": "A", "email": "dup@example.com"})
    resp = client.post("/auth/register", data={"shop_name": "B", "full_name": "B", "email": "dup@example.com"})
    assert resp.status_code == 400
    assert "déjà utilisé" in resp.json()["detail"]


def test_login_while_shop_pending_returns_403(client, db_session):
    shop = Shop(name="Pending Shop", status=ShopStatus.PENDING)
    db_session.add(shop)
    db_session.commit()
    db_session.refresh(shop)
    user = User(shop_id=shop.id, full_name="X", email="pending@example.com", hashed_password=hash_password("Secret123"), is_active=True)
    db_session.add(user)
    db_session.commit()

    resp = client.post("/auth/login", json={"email": "pending@example.com", "password": "Secret123"})
    assert resp.status_code == 403
    assert "en cours de traitement" in resp.json()["detail"]


def test_login_while_shop_rejected_returns_403(client, db_session):
    shop = Shop(name="Rejected Shop", status=ShopStatus.REJECTED)
    db_session.add(shop)
    db_session.commit()
    db_session.refresh(shop)
    user = User(shop_id=shop.id, full_name="X", email="rejected@example.com", hashed_password=hash_password("Secret123"), is_active=True)
    db_session.add(user)
    db_session.commit()

    resp = client.post("/auth/login", json={"email": "rejected@example.com", "password": "Secret123"})
    assert resp.status_code == 403
    assert "rejetée" in resp.json()["detail"]


def test_login_unknown_email_returns_401(client):
    resp = client.post("/auth/login", json={"email": "unknown@example.com", "password": "x"})
    assert resp.status_code == 401


def test_login_wrong_password_returns_401(client, owner):
    resp = client.post("/auth/login", json={"email": owner.email, "password": "wrong"})
    assert resp.status_code == 401


def test_login_inactive_account_returns_403(client, db_session, shop):
    user = User(shop_id=shop.id, full_name="X", email="inactive@example.com", hashed_password=hash_password("Secret123"), is_active=False)
    db_session.add(user)
    db_session.commit()
    resp = client.post("/auth/login", json={"email": "inactive@example.com", "password": "Secret123"})
    assert resp.status_code == 403
    assert "désactivé" in resp.json()["detail"]


def test_login_success_returns_token(client, db_session, shop):
    user = User(shop_id=shop.id, full_name="X", email="ok@example.com", hashed_password=hash_password("Secret123"), is_active=True)
    db_session.add(user)
    db_session.commit()
    resp = client.post("/auth/login", json={"email": "ok@example.com", "password": "Secret123"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_me_returns_user_and_shop(client, auth_headers, owner, shop):
    resp = client.get("/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == owner.email
    assert body["shop"]["id"] == shop.id


def test_change_password_wrong_current_returns_401(client, auth_headers):
    resp = client.post("/auth/change-password", headers=auth_headers, json={"current_password": "wrong", "new_password": "NouveauMdp1"})
    assert resp.status_code == 401


def test_change_password_too_short_returns_400(client, auth_headers):
    resp = client.post("/auth/change-password", headers=auth_headers, json={"current_password": "Test1234!", "new_password": "abc"})
    assert resp.status_code == 400
    assert "nouveau mot de passe" in resp.json()["detail"]


def test_change_password_success(client, auth_headers, owner):
    resp = client.post("/auth/change-password", headers=auth_headers, json={"current_password": "Test1234!", "new_password": "NouveauMdp1"})
    assert resp.status_code == 204
    relogin = client.post("/auth/login", json={"email": owner.email, "password": "NouveauMdp1"})
    assert relogin.status_code == 200


def test_update_shop_partial_and_empty_string_clears_field(client, auth_headers, shop, db_session):
    shop.address = "Ancienne Adresse"
    db_session.commit()

    resp = client.patch("/auth/shop", headers=auth_headers, json={"address": ""})
    assert resp.status_code == 200
    assert resp.json()["address"] is None


def test_employee_can_update_own_profile(client, employee_headers, employee):
    resp = client.patch(
        "/auth/me",
        headers=employee_headers,
        json={"full_name": "Nouveau Nom", "phone": "780000099", "email": "nouveau@example.com"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["full_name"] == "Nouveau Nom"
    assert body["phone"] == "780000099"
    assert body["email"] == "nouveau@example.com"


def test_owner_can_update_own_profile(client, auth_headers, owner):
    resp = client.patch("/auth/me", headers=auth_headers, json={"full_name": "Nouveau Owner"})
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Nouveau Owner"


def test_update_me_empty_full_name_returns_400(client, employee_headers):
    resp = client.patch("/auth/me", headers=employee_headers, json={"full_name": "  "})
    assert resp.status_code == 400


def test_update_me_duplicate_email_returns_400(client, employee_headers, owner):
    resp = client.patch("/auth/me", headers=employee_headers, json={"email": owner.email})
    assert resp.status_code == 400
    assert "déjà utilisé" in resp.json()["detail"]


def test_forgot_password_check_unknown_phone_returns_404(client):
    resp = client.post("/auth/forgot-password/check", json={"phone": "779999999"})
    assert resp.status_code == 404


def test_forgot_password_check_known_phone_returns_200(client, db_session, owner, shop):
    shop.phone = "771112233"
    db_session.commit()
    resp = client.post("/auth/forgot-password/check", json={"phone": "771112233"})
    assert resp.status_code == 200
    assert resp.json()["shop_name"] == shop.name


def test_forgot_password_reset_too_short_returns_400(client, db_session, owner, shop):
    shop.phone = "771112233"
    db_session.commit()
    resp = client.post("/auth/forgot-password/reset", json={"phone": "771112233", "new_password": "abc"})
    assert resp.status_code == 400
    assert "mot de passe" in resp.json()["detail"]


def test_forgot_password_reset_unknown_phone_returns_404(client):
    resp = client.post("/auth/forgot-password/reset", json={"phone": "770000000", "new_password": "NouveauMdp1"})
    assert resp.status_code == 404


def test_forgot_password_reset_success_allows_relogin(client, db_session, owner, shop):
    shop.phone = "771112233"
    db_session.commit()
    resp = client.post("/auth/forgot-password/reset", json={"phone": "771112233", "new_password": "ApresReset1"})
    assert resp.status_code == 204

    relogin = client.post("/auth/login", json={"email": owner.email, "password": "ApresReset1"})
    assert relogin.status_code == 200
