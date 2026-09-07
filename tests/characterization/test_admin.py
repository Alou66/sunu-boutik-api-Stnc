"""Caractérise /admin/* (module admin) : vue d'ensemble, liste des boutiques
filtrée par statut, statistiques par boutique, approbation/rejet, contrôle
d'accès réservé aux administrateurs.

Réf. app/modules/admin/admin_service.py — aucun test de caractérisation
n'existait pour ce routeur avant la migration ; ce fichier ferme ce trou.
"""
from app.modules.identity.identity_model import Shop, ShopStatus, User


def _pending_shop_with_owner(db_session, name="Boutique En Attente", phone=None):
    shop = Shop(name=name, phone=phone, status=ShopStatus.PENDING)
    db_session.add(shop)
    db_session.commit()
    db_session.refresh(shop)
    owner = User(shop_id=shop.id, full_name="Propriétaire", email=f"owner{shop.id}@example.com", is_active=False)
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return shop, owner


def test_overview_counts_shops_by_status(client, admin_headers, db_session, shop):
    _pending_shop_with_owner(db_session)
    resp = client.get("/admin/overview", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_shops"] == 2
    assert body["approved_shops"] == 1
    assert body["pending_shops"] == 1


def test_list_shops_filtered_by_status_includes_owner_info(client, admin_headers, db_session):
    shop, owner = _pending_shop_with_owner(db_session)
    resp = client.get("/admin/shops", headers=admin_headers, params={"status_filter": "pending"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["owner_email"] == owner.email


def test_shop_stats_not_found_returns_404(client, admin_headers):
    resp = client.get("/admin/shops/999999/stats", headers=admin_headers)
    assert resp.status_code == 404


def test_shop_stats_returns_counts(client, admin_headers, shop, owner, simple_product):
    resp = client.get(f"/admin/shops/{shop.id}/stats", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["shop_id"] == shop.id
    assert body["products_count"] == 1
    assert body["users_count"] == 1


def test_approve_shop_activates_owner_and_sets_temp_password(client, admin_headers, db_session):
    shop, owner = _pending_shop_with_owner(db_session)
    resp = client.post(f"/admin/shops/{shop.id}/approve", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    db_session.refresh(shop)
    db_session.refresh(owner)
    assert shop.status == ShopStatus.APPROVED
    assert owner.is_active is True
    assert owner.hashed_password is not None
    assert owner.must_change_password is True


def test_approve_shop_not_found_returns_404(client, admin_headers):
    resp = client.post("/admin/shops/999999/approve", headers=admin_headers)
    assert resp.status_code == 404


def test_reject_shop_deactivates_all_users(client, admin_headers, db_session):
    shop, owner = _pending_shop_with_owner(db_session)
    resp = client.post(f"/admin/shops/{shop.id}/reject", headers=admin_headers, json={"reason": "Documents incomplets"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    db_session.refresh(shop)
    db_session.refresh(owner)
    assert shop.status == ShopStatus.REJECTED
    assert owner.is_active is False


def test_reject_shop_without_owner_does_not_crash(client, admin_headers, db_session):
    shop = Shop(name="Boutique Sans Propriétaire", status=ShopStatus.PENDING)
    db_session.add(shop)
    db_session.commit()
    db_session.refresh(shop)
    resp = client.post(f"/admin/shops/{shop.id}/reject", headers=admin_headers, json={})
    assert resp.status_code == 200
    assert resp.json()["owner_email"] is None


def test_non_admin_access_returns_403(client, auth_headers):
    resp = client.get("/admin/overview", headers=auth_headers)
    assert resp.status_code == 403


def test_unauthenticated_access_returns_401(client):
    resp = client.get("/admin/overview")
    assert resp.status_code == 401
