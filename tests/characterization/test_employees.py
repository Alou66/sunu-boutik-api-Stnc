"""Caractérise le module Employés : CRUD (réservé au propriétaire), restriction
des routes Employés/Profil boutique/Statistiques pour un EMPLOYEE, et surtout
l'invalidation de session à la désactivation (voir core/deps.get_current_user
et employees_service.EmployeeService.update).

Le propriétaire ne peut modifier que le compte de l'employé (mot de passe,
activation) : nom/téléphone/email appartiennent à l'employé et ne se modifient
que via PATCH /auth/me (voir test_identity_profile.py).
"""
from app.core.security import create_access_token
from app.modules.identity.identity_model import User, UserRole
from app.modules.stock_receipts.stock_receipts_model import StockReceipt


def test_owner_can_create_list_update_employee(client, auth_headers, shop):
    resp = client.post(
        "/employees",
        headers=auth_headers,
        json={"full_name": "Awa Diop", "phone": "771234567", "email": "awa@example.com", "password": "Secret123"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "employee"
    assert body["is_active"] is True
    # Le mot de passe est choisi par le propriétaire : l'employé doit le
    # changer avant d'accéder réellement à l'application (voir /auth/me,
    # /auth/change-password et le garde-fou dashboard/layout.tsx côté front).
    assert body["must_change_password"] is True

    listing = client.get("/employees", headers=auth_headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    resp = client.patch(f"/employees/{body['id']}", headers=auth_headers, json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_owner_cannot_change_employee_personal_info(client, auth_headers, employee):
    # Nom, téléphone et email appartiennent à l'employé : le propriétaire ne
    # peut plus les modifier depuis /employees (champs simplement ignorés,
    # EmployeeUpdate ne les expose plus), seul le compte (mot de passe,
    # activation) reste sous son contrôle.
    resp = client.patch(
        f"/employees/{employee.id}",
        headers=auth_headers,
        json={"full_name": "Autre nom", "phone": "780000000", "email": "autre@example.com"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["full_name"] == employee.full_name
    assert body["phone"] == employee.phone
    assert body["email"] == employee.email


def test_create_employee_missing_phone_returns_400(client, auth_headers):
    resp = client.post(
        "/employees",
        headers=auth_headers,
        json={"full_name": "Awa Diop", "phone": "  ", "email": "awa2@example.com", "password": "Secret123"},
    )
    assert resp.status_code == 400


def test_create_employee_duplicate_email_returns_400(client, auth_headers, employee):
    resp = client.post(
        "/employees",
        headers=auth_headers,
        json={"full_name": "Autre", "phone": "770000002", "email": employee.email, "password": "Secret123"},
    )
    assert resp.status_code == 400
    assert "déjà utilisé" in resp.json()["detail"]


def test_owner_can_delete_employee(client, auth_headers, employee):
    resp = client.delete(f"/employees/{employee.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_delete_employee_with_related_records_returns_400(client, auth_headers, employee, shop, db_session):
    receipt = StockReceipt(shop_id=shop.id, created_by_id=employee.id)
    db_session.add(receipt)
    db_session.commit()

    resp = client.delete(f"/employees/{employee.id}", headers=auth_headers)
    assert resp.status_code == 400
    assert "opérations associées" in resp.json()["detail"]


def test_employee_must_change_password_on_first_login_then_can_use_new_one(client, auth_headers, db_session):
    resp = client.post(
        "/employees",
        headers=auth_headers,
        json={"full_name": "Bineta Sow", "phone": "771112233", "email": "bineta@example.com", "password": "Secret123"},
    )
    employee_id = resp.json()["id"]

    login = client.post("/auth/login", json={"email": "bineta@example.com", "password": "Secret123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    me = client.get("/auth/me", headers=headers)
    assert me.json()["user"]["must_change_password"] is True

    changed = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": "Secret123", "new_password": "NouveauMdp1"},
    )
    assert changed.status_code == 204

    # Étape 0.1.2 : un changement de mot de passe incrémente token_version, donc
    # le JWT utilisé jusqu'ici est refusé (il fallait auparavant le réutiliser).
    assert client.get("/auth/me", headers=headers).status_code == 401

    relogin = client.post("/auth/login", json={"email": "bineta@example.com", "password": "NouveauMdp1"})
    assert relogin.status_code == 200
    relogin_me = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {relogin.json()['access_token']}"}
    )
    assert relogin_me.json()["user"]["must_change_password"] is False
    assert relogin_me.json()["user"]["id"] == employee_id


def test_owner_resetting_employee_password_forces_change_again(client, auth_headers, employee, db_session):
    employee.must_change_password = False
    db_session.commit()

    resp = client.patch(f"/employees/{employee.id}", headers=auth_headers, json={"password": "NouveauMdp1"})
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is True


def test_employee_cannot_access_employees_module(client, employee_headers):
    resp = client.get("/employees", headers=employee_headers)
    assert resp.status_code == 403


def test_employee_cannot_access_statistics(client, employee_headers):
    resp = client.get("/statistics?date_from=2026-01-01&date_to=2026-01-31", headers=employee_headers)
    assert resp.status_code == 403


def test_employee_cannot_update_shop_profile(client, employee_headers):
    resp = client.patch("/auth/shop", headers=employee_headers, json={"name": "Nouveau nom"})
    assert resp.status_code == 403


def test_employee_can_access_business_modules(client, employee_headers):
    resp = client.get("/suppliers", headers=employee_headers)
    assert resp.status_code == 200


def test_owner_can_access_employees_statistics_and_profile(client, auth_headers):
    assert client.get("/employees", headers=auth_headers).status_code == 200
    assert client.get("/statistics?date_from=2026-01-01&date_to=2026-01-31", headers=auth_headers).status_code == 200
    assert client.patch("/auth/shop", headers=auth_headers, json={}).status_code == 200


def test_deactivating_employee_invalidates_current_session_immediately(client, auth_headers, employee, db_session):
    token = create_access_token({"sub": str(employee.id), "tv": employee.token_version})
    employee_headers = {"Authorization": f"Bearer {token}"}

    # La session de l'employé est valide avant désactivation.
    assert client.get("/suppliers", headers=employee_headers).status_code == 200

    resp = client.patch(f"/employees/{employee.id}", headers=auth_headers, json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # Même token, requête suivante : refusé, sans nouvelle connexion.
    resp = client.get("/suppliers", headers=employee_headers)
    assert resp.status_code == 401
    assert "désactivé" in resp.json()["detail"]

    # Réactivation : l'ANCIEN token reste invalide (pas de restauration automatique de session).
    resp = client.patch(f"/employees/{employee.id}", headers=auth_headers, json={"is_active": True})
    assert resp.status_code == 200
    resp = client.get("/suppliers", headers=employee_headers)
    assert resp.status_code == 401

    # Une nouvelle connexion (nouveau token) fonctionne de nouveau.
    login = client.post("/auth/login", json={"email": employee.email, "password": "Test1234!"})
    assert login.status_code == 200
    new_token = login.json()["access_token"]
    resp = client.get("/suppliers", headers={"Authorization": f"Bearer {new_token}"})
    assert resp.status_code == 200
