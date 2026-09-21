"""Caractérise l'invalidation des JWT via `token_version` (étape 0.1.2).

Chaque test suit le même scénario, exercé par de vraies requêtes
authentifiées (et pas seulement par une lecture de `users.token_version`) :
login → JWT → opération critique → l'ANCIEN JWT est refusé en 401 → nouveau
login → le NOUVEAU JWT fonctionne.

Réf. app/core/deps.py::get_current_user (compare le claim "tv" du JWT à
users.token_version) et les services qui incrémentent ce compteur :
IdentityService.change_password / confirm_password_reset,
EmployeeService.update, AdminService.reset_owner_password,
AdminRepository.deactivate_all_users (suspension et rejet d'une boutique).
"""
import pytest

from app.core.security import hash_password
from app.modules.identity.identity_model import Shop, ShopStatus, User, UserRole

OLD_PASSWORD = "Test1234!"  # mot de passe des fixtures owner / employee (conftest.py)
NEW_PASSWORD = "NouveauMdp1"


def _login(client, email, password):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _assert_session_works(client, headers):
    resp = client.get("/auth/me", headers=headers)
    assert resp.status_code == 200, resp.text


def _assert_session_revoked(client, headers):
    resp = client.get("/auth/me", headers=headers)
    assert resp.status_code == 401, resp.text


# ---- Changement de mot de passe (utilisateur concerné) ----


@pytest.mark.parametrize("who", ["owner", "employee"])
def test_change_password_invalidates_old_jwt(client, request, who):
    user = request.getfixturevalue(who)
    old_headers = _login(client, user.email, OLD_PASSWORD)
    _assert_session_works(client, old_headers)

    resp = client.post(
        "/auth/change-password",
        headers=old_headers,
        json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 204

    _assert_session_revoked(client, old_headers)

    # L'ancien mot de passe n'ouvre plus de session, le nouveau si.
    assert client.post("/auth/login", json={"email": user.email, "password": OLD_PASSWORD}).status_code == 401
    new_headers = _login(client, user.email, NEW_PASSWORD)
    _assert_session_works(client, new_headers)
    assert new_headers != old_headers


def test_revoked_session_message_is_not_the_account_disabled_message(client, owner, employee, auth_headers):
    # Session coupée par un changement de mot de passe : le compte est ACTIF, le
    # message doit inviter à se reconnecter (et non parler de compte désactivé).
    employee_headers = _login(client, employee.email, OLD_PASSWORD)
    resp = client.patch(f"/employees/{employee.id}", headers=auth_headers, json={"password": NEW_PASSWORD})
    assert resp.status_code == 200

    revoked = client.get("/auth/me", headers=employee_headers)
    assert revoked.status_code == 401
    assert "reconnecter" in revoked.json()["detail"]
    assert "désactivé" not in revoked.json()["detail"]

    # Un compte réellement désactivé garde son message dédié.
    resp = client.patch(f"/employees/{employee.id}", headers=auth_headers, json={"is_active": False})
    assert resp.status_code == 200
    disabled = client.get("/auth/me", headers=employee_headers)
    assert disabled.status_code == 401
    assert "désactivé" in disabled.json()["detail"]


def test_change_password_does_not_touch_other_users_sessions(client, owner, employee):
    owner_headers = _login(client, owner.email, OLD_PASSWORD)
    employee_headers = _login(client, employee.email, OLD_PASSWORD)

    resp = client.post(
        "/auth/change-password",
        headers=employee_headers,
        json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 204

    _assert_session_revoked(client, employee_headers)
    _assert_session_works(client, owner_headers)


def test_token_version_is_not_exposed_in_public_dto(client, auth_headers):
    body = client.get("/auth/me", headers=auth_headers).json()
    assert "token_version" not in body["user"]
    assert "hashed_password" not in body["user"]


# ---- Réinitialisation de mot de passe (par e-mail + code) ----


def test_forgot_password_reset_invalidates_old_jwt(client, owner, monkeypatch):
    monkeypatch.setattr("app.modules.identity.identity_service.generate_reset_code", lambda: "123456")
    monkeypatch.setattr("app.core.email.send_email", lambda *args, **kwargs: None)
    old_headers = _login(client, owner.email, OLD_PASSWORD)

    assert client.post("/auth/forgot-password/request", json={"email": owner.email}).status_code == 200
    resp = client.post(
        "/auth/forgot-password/confirm",
        json={"email": owner.email, "code": "123456", "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 204

    _assert_session_revoked(client, old_headers)
    _assert_session_works(client, _login(client, owner.email, NEW_PASSWORD))


# ---- Le propriétaire change le mot de passe d'un employé ----


def test_owner_setting_employee_password_invalidates_employee_jwt(client, auth_headers, employee):
    old_headers = _login(client, employee.email, OLD_PASSWORD)
    _assert_session_works(client, old_headers)

    resp = client.patch(f"/employees/{employee.id}", headers=auth_headers, json={"password": NEW_PASSWORD})
    assert resp.status_code == 200

    _assert_session_revoked(client, old_headers)
    assert client.post("/auth/login", json={"email": employee.email, "password": OLD_PASSWORD}).status_code == 401
    _assert_session_works(client, _login(client, employee.email, NEW_PASSWORD))


def test_owner_updating_employee_without_password_keeps_employee_jwt(client, auth_headers, employee):
    # Un PATCH qui ne change pas le mot de passe (ex: is_active inchangé) ne
    # doit pas couper la session de l'employé.
    employee_headers = _login(client, employee.email, OLD_PASSWORD)
    resp = client.patch(f"/employees/{employee.id}", headers=auth_headers, json={"is_active": True})
    assert resp.status_code == 200
    _assert_session_works(client, employee_headers)


# ---- Réinitialisation du mot de passe du propriétaire par l'admin ----


def test_admin_owner_password_reset_invalidates_owner_jwt(client, admin_headers, owner, shop, monkeypatch):
    monkeypatch.setattr("app.modules.admin.admin_service.generate_temp_password", lambda: "TempPass99")
    old_headers = _login(client, owner.email, OLD_PASSWORD)

    resp = client.post(f"/admin/shops/{shop.id}/owner/reset-password", headers=admin_headers)
    assert resp.status_code == 200

    _assert_session_revoked(client, old_headers)
    _assert_session_works(client, _login(client, owner.email, "TempPass99"))


# ---- Suspension d'une boutique ----


def test_suspending_shop_invalidates_owner_and_employee_jwt_even_after_reactivation(
    client, admin_headers, owner, employee, shop
):
    owner_headers = _login(client, owner.email, OLD_PASSWORD)
    employee_headers = _login(client, employee.email, OLD_PASSWORD)
    _assert_session_works(client, owner_headers)
    _assert_session_works(client, employee_headers)

    resp = client.patch(f"/admin/shops/{shop.id}/suspend", headers=admin_headers, json={"reason": "Impayé"})
    assert resp.status_code == 200
    _assert_session_revoked(client, owner_headers)
    _assert_session_revoked(client, employee_headers)

    resp = client.patch(f"/admin/shops/{shop.id}/reactivate", headers=admin_headers)
    assert resp.status_code == 200

    # Comptes de nouveau actifs, mais les tokens émis avant la suspension restent refusés.
    _assert_session_revoked(client, owner_headers)
    _assert_session_revoked(client, employee_headers)

    _assert_session_works(client, _login(client, owner.email, OLD_PASSWORD))
    _assert_session_works(client, _login(client, employee.email, OLD_PASSWORD))


# ---- Rejet / désactivation d'une boutique ----


def test_rejecting_shop_invalidates_jwt_even_after_later_approval(
    client, admin_headers, owner, employee, shop, monkeypatch
):
    monkeypatch.setattr("app.modules.admin.admin_service.generate_temp_password", lambda: "TempPass99")
    owner_headers = _login(client, owner.email, OLD_PASSWORD)
    employee_headers = _login(client, employee.email, OLD_PASSWORD)

    resp = client.post(f"/admin/shops/{shop.id}/reject", headers=admin_headers, json={"reason": "Dossier incomplet"})
    assert resp.status_code == 200
    _assert_session_revoked(client, owner_headers)
    _assert_session_revoked(client, employee_headers)

    # Une approbation ultérieure réactive les comptes : les anciens tokens ne reviennent pas.
    resp = client.post(f"/admin/shops/{shop.id}/approve", headers=admin_headers)
    assert resp.status_code == 200
    _assert_session_revoked(client, owner_headers)
    _assert_session_revoked(client, employee_headers)

    _assert_session_works(client, _login(client, owner.email, "TempPass99"))
    _assert_session_works(client, _login(client, employee.email, OLD_PASSWORD))


def test_rejecting_shop_only_affects_that_shops_users(client, admin_headers, db_session, owner, shop):
    other_shop = Shop(name="Autre Boutique", status=ShopStatus.APPROVED)
    db_session.add(other_shop)
    db_session.commit()
    other_owner = User(
        shop_id=other_shop.id,
        full_name="Autre Propriétaire",
        email="other-owner@example.com",
        hashed_password=hash_password(OLD_PASSWORD),
        role=UserRole.OWNER,
        is_active=True,
    )
    db_session.add(other_owner)
    db_session.commit()

    owner_headers = _login(client, owner.email, OLD_PASSWORD)
    other_headers = _login(client, other_owner.email, OLD_PASSWORD)

    resp = client.post(f"/admin/shops/{shop.id}/reject", headers=admin_headers, json={})
    assert resp.status_code == 200

    _assert_session_revoked(client, owner_headers)
    _assert_session_works(client, other_headers)
