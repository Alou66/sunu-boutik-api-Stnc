"""Caractérise l'unicité des noms d'articles (shop_id, upper(name)) et de
catégories (shop_id, lower(name)) par boutique (étape 0.1.8).

Deux niveaux sont exercés :
  - la couche API existante : DuplicateProductNameError -> 409 (articles),
    DuplicateCategoryNameError -> 400 (catégories, statut historique conservé) ;
  - l'index unique en base, filet de sécurité que l'API ne voit pas : ligne
    historique en casse mixte, insertion directe, création simultanée du même
    nom (les deux requêtes passent le contrôle applicatif, l'index tranche et
    IntegrityError est converti en erreur métier, jamais en 500).

Réf. app/modules/products/products_model.py (uq_products_shop_id_upper_name),
app/modules/categories/categories_model.py (uq_categories_shop_id_lower_name),
migration alembic e7b1c4d9a2f3.
"""
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.security import create_access_token, hash_password
from app.main import app
from app.modules.categories.categories_model import Category
from app.modules.categories.categories_repository import CategoryRepository
from app.modules.identity.identity_model import Shop, ShopStatus, User, UserRole
from app.modules.products.products_model import Product
from app.modules.products.products_repository import ProductRepository


@pytest.fixture
def other_shop_headers(db_session):
    shop = Shop(name="Autre Boutique", status=ShopStatus.APPROVED)
    db_session.add(shop)
    db_session.commit()
    db_session.refresh(shop)
    user = User(
        shop_id=shop.id,
        full_name="Autre Propriétaire",
        email="autre-owner@example.com",
        hashed_password=hash_password("Test1234!"),
        role=UserRole.OWNER,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token({"sub": str(user.id), "tv": user.token_version})
    return {"Authorization": f"Bearer {token}"}


def _create_category(client, headers, name):
    resp = client.post("/categories", headers=headers, json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _product_payload(category_id, name):
    return {"name": name, "category_id": category_id, "unit_price": 500}


def _post_parallel(path, headers, payload):
    results = {}
    barrier = threading.Barrier(2)

    def _post(index):
        with TestClient(app) as local_client:
            barrier.wait(timeout=5)
            results[index] = local_client.post(path, headers=headers, json=payload)

    threads = [threading.Thread(target=_post, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    return results


# ---- Articles : (shop_id, upper(name)) ----


def test_product_same_name_same_shop_returns_409(client, auth_headers, category):
    first = client.post("/products", headers=auth_headers, json=_product_payload(category.id, "Riz"))
    assert first.status_code == 201

    second = client.post("/products", headers=auth_headers, json=_product_payload(category.id, "Riz"))
    assert second.status_code == 409
    assert "existe déjà" in second.json()["detail"]


@pytest.mark.parametrize("variant", ["riz", "RIZ", "  rIz  "])
def test_product_case_variants_of_existing_name_return_409(client, auth_headers, category, variant):
    assert client.post("/products", headers=auth_headers, json=_product_payload(category.id, "Riz")).status_code == 201

    resp = client.post("/products", headers=auth_headers, json=_product_payload(category.id, variant))

    assert resp.status_code == 409
    assert client.get("/products", headers=auth_headers).json()["total"] == 1


def test_product_same_name_in_another_shop_is_allowed(client, auth_headers, other_shop_headers, category):
    other_category = _create_category(client, other_shop_headers, "GENERAL")
    assert client.post("/products", headers=auth_headers, json=_product_payload(category.id, "Riz")).status_code == 201

    resp = client.post("/products", headers=other_shop_headers, json=_product_payload(other_category["id"], "Riz"))

    assert resp.status_code == 201


def test_product_legacy_mixed_case_row_conflicts_with_api_name(
    client, auth_headers, db_session, shop, category, product_repo
):
    # Ligne historique créée avant la normalisation en majuscules des DTO : "Riz".
    # L'API normalise "riz" en "RIZ" ; l'ancien contrôle (égalité stricte) ne voyait
    # pas le conflit, le contrôle insensible à la casse et l'index le voient.
    db_session.add(Product(shop_id=shop.id, category_id=category.id, name="Riz", unit_price=1, quantity=0))
    db_session.commit()
    assert product_repo.exists_with_name(shop.id, "RIZ") is True

    resp = client.post("/products", headers=auth_headers, json=_product_payload(category.id, "riz"))

    assert resp.status_code == 409


def test_product_update_to_existing_name_variant_returns_409(client, auth_headers, category):
    client.post("/products", headers=auth_headers, json=_product_payload(category.id, "Riz"))
    other = client.post("/products", headers=auth_headers, json=_product_payload(category.id, "Sucre")).json()

    resp = client.patch(f"/products/{other['id']}", headers=auth_headers, json={"name": "riz"})

    assert resp.status_code == 409
    assert client.get(f"/products/{other['id']}", headers=auth_headers).json()["name"] == "SUCRE"


def test_product_unique_index_rejects_case_variants_in_same_shop_only(db_session, shop, category):
    other_shop = Shop(name="Autre", status=ShopStatus.APPROVED)
    db_session.add(other_shop)
    db_session.commit()
    other_category = Category(shop_id=other_shop.id, name="GENERAL")
    db_session.add(other_category)
    db_session.commit()

    db_session.add(Product(shop_id=shop.id, category_id=category.id, name="Riz", unit_price=1, quantity=0))
    db_session.commit()

    db_session.add(Product(shop_id=shop.id, category_id=category.id, name="RIZ", unit_price=1, quantity=0))
    with pytest.raises(IntegrityError) as excinfo:
        db_session.commit()
    db_session.rollback()
    assert excinfo.value.orig.diag.constraint_name == "uq_products_shop_id_upper_name"

    db_session.add(Product(shop_id=other_shop.id, category_id=other_category.id, name="RIZ", unit_price=1, quantity=0))
    db_session.commit()  # autre boutique : autorisé


def test_product_duplicate_bypassing_app_check_still_returns_409_not_500(
    client, auth_headers, category, monkeypatch
):
    client.post("/products", headers=auth_headers, json=_product_payload(category.id, "Riz"))
    # Simule la course : le contrôle applicatif ne voit pas le doublon, seul l'index le voit.
    monkeypatch.setattr(ProductRepository, "exists_with_name", lambda *args, **kwargs: False)

    resp = client.post("/products", headers=auth_headers, json=_product_payload(category.id, "Riz"))

    assert resp.status_code == 409
    assert "existe déjà" in resp.json()["detail"]


def test_product_concurrent_creation_of_same_name_creates_only_one(client, auth_headers, category):
    results = _post_parallel("/products", auth_headers, _product_payload(category.id, "Riz"))

    assert sorted(r.status_code for r in results.values()) == [201, 409], {i: r.text for i, r in results.items()}
    assert client.get("/products", headers=auth_headers).json()["total"] == 1


# ---- Catégories : (shop_id, lower(name)) ----


def test_category_same_name_same_shop_returns_400(client, auth_headers):
    _create_category(client, auth_headers, "Sucre")

    resp = client.post("/categories", headers=auth_headers, json={"name": "Sucre"})

    assert resp.status_code == 400
    assert "existe déjà" in resp.json()["detail"]


@pytest.mark.parametrize("variant", ["sucre", "SUCRE", "  sUcRe "])
def test_category_case_variants_of_existing_name_are_refused(client, auth_headers, variant):
    _create_category(client, auth_headers, "Sucre")

    resp = client.post("/categories", headers=auth_headers, json={"name": variant})

    assert resp.status_code == 400
    assert client.get("/categories", headers=auth_headers).json()["total"] == 1


def test_category_same_name_in_another_shop_is_allowed(client, auth_headers, other_shop_headers):
    _create_category(client, auth_headers, "Sucre")

    resp = client.post("/categories", headers=other_shop_headers, json={"name": "Sucre"})

    assert resp.status_code == 201


def test_category_update_to_existing_name_variant_is_refused(client, auth_headers):
    _create_category(client, auth_headers, "Sucre")
    other = _create_category(client, auth_headers, "Riz")

    resp = client.patch(f"/categories/{other['id']}", headers=auth_headers, json={"name": "sucre"})

    assert resp.status_code == 400
    assert client.get(f"/categories/{other['id']}", headers=auth_headers).json()["name"] == "RIZ"


def test_category_unique_index_rejects_case_variants_in_same_shop_only(db_session, shop):
    other_shop = Shop(name="Autre", status=ShopStatus.APPROVED)
    db_session.add(other_shop)
    db_session.commit()

    db_session.add(Category(shop_id=shop.id, name="Sucre"))
    db_session.commit()

    for variant in ("sucre", "SUCRE"):
        db_session.add(Category(shop_id=shop.id, name=variant))
        with pytest.raises(IntegrityError) as excinfo:
            db_session.commit()
        db_session.rollback()
        assert excinfo.value.orig.diag.constraint_name == "uq_categories_shop_id_lower_name"

    db_session.add(Category(shop_id=other_shop.id, name="SUCRE"))
    db_session.commit()  # autre boutique : autorisé


def test_category_duplicate_bypassing_app_check_is_refused_not_500(client, auth_headers, monkeypatch):
    _create_category(client, auth_headers, "Sucre")
    monkeypatch.setattr(CategoryRepository, "exists_with_name", lambda *args, **kwargs: False)

    resp = client.post("/categories", headers=auth_headers, json={"name": "Sucre"})

    assert resp.status_code == 400
    assert "existe déjà" in resp.json()["detail"]


def test_category_concurrent_creation_of_same_name_creates_only_one(client, auth_headers):
    results = _post_parallel("/categories", auth_headers, {"name": "Sucre"})

    assert sorted(r.status_code for r in results.values()) == [201, 400], {i: r.text for i, r in results.items()}
    assert client.get("/categories", headers=auth_headers).json()["total"] == 1
