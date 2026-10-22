"""Caractérise le module Initialisation du stock.

Règles : seuls les produits/formes non initialisés et n'ayant reçu aucun
approvisionnement validé apparaissent. Quantité vide ignorée, zéro produit
une erreur explicite, > 0 requis. Une forme ne peut être initialisée qu'une
fois. Isolation par boutique, mouvements tracés, transactions atomiques.
"""


def _init_resp(client, auth_headers, lines):
    return client.post("/stock-initializations", headers=auth_headers, json={"lines": lines})


def test_new_product_appears_in_pending(client, auth_headers, simple_product):
    resp = client.get("/stock-initializations/pending", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    # simple_product is non-transformable, form principale pending
    assert any(i["product_id"] == simple_product.id and i["unit_target"] == "principale" for i in items)


def test_non_transformable_has_only_principale(client, auth_headers, simple_product):
    resp = client.get("/stock-initializations/pending", headers=auth_headers)
    items = resp.json()["items"]
    forms = [i for i in items if i["product_id"] == simple_product.id]
    assert len(forms) == 1
    assert forms[0]["unit_target"] == "principale"


def test_transformable_has_principale_and_secondaire(client, auth_headers, transformable_product):
    resp = client.get("/stock-initializations/pending", headers=auth_headers)
    items = resp.json()["items"]
    forms = [i for i in items if i["product_id"] == transformable_product.id]
    targets = {f["unit_target"] for f in forms}
    assert targets == {"principale", "secondaire"}


def test_empty_quantity_ignored_zero_errors(client, auth_headers, simple_product):
    # empty string-like via null/omitted - send null
    resp = _init_resp(client, auth_headers, [{"product_id": simple_product.id, "unit_target": "principale", "quantity": None}])
    assert resp.status_code == 400


def test_zero_quantity_explicit_error(client, auth_headers, simple_product):
    resp = _init_resp(client, auth_headers, [{"product_id": simple_product.id, "unit_target": "principale", "quantity": 0}])
    assert resp.status_code == 400
    assert "zéro" in resp.json()["detail"].lower()


def test_positive_quantity_required(client, auth_headers, simple_product):
    resp = _init_resp(client, auth_headers, [{"product_id": simple_product.id, "unit_target": "principale", "quantity": -5}])
    assert resp.status_code == 400


def test_partial_initialization_keeps_other_form(client, auth_headers, db_session, transformable_product):
    # initialize only principale
    resp = _init_resp(client, auth_headers, [{"product_id": transformable_product.id, "unit_target": "principale", "quantity": 10}])
    assert resp.status_code == 201
    db_session.refresh(transformable_product)
    assert transformable_product.quantity == 13  # 3 + 10

    # produit still visible because secondaire not initialized
    pending = client.get("/stock-initializations/pending", headers=auth_headers).json()["items"]
    forms = [i for i in pending if i["product_id"] == transformable_product.id]
    assert len(forms) == 1
    assert forms[0]["unit_target"] == "secondaire"


def test_form_disappears_after_initialization(client, auth_headers, simple_product):
    _init_resp(client, auth_headers, [{"product_id": simple_product.id, "unit_target": "principale", "quantity": 5}])
    pending = client.get("/stock-initializations/pending", headers=auth_headers).json()["items"]
    assert not any(i["product_id"] == simple_product.id for i in pending)


def test_form_disappears_after_validated_receipt(client, auth_headers, simple_product):
    # create and validate receipt for this form
    created = client.post(
        "/stock-receipts",
        headers=auth_headers,
        json={"supplier_id": None, "reference": None, "note": None, "lines": [{"product_id": simple_product.id, "unit_target": "principale", "quantity": 2, "unit_cost": 100}]},
    ).json()
    client.post(f"/stock-receipts/{created['id']}/validate", headers=auth_headers)
    pending = client.get("/stock-initializations/pending", headers=auth_headers).json()["items"]
    assert not any(i["product_id"] == simple_product.id for i in pending)


def test_cannot_initialize_twice(client, auth_headers, simple_product):
    resp1 = _init_resp(client, auth_headers, [{"product_id": simple_product.id, "unit_target": "principale", "quantity": 5}])
    assert resp1.status_code == 201
    resp2 = _init_resp(client, auth_headers, [{"product_id": simple_product.id, "unit_target": "principale", "quantity": 3}])
    assert resp2.status_code == 400


def test_isolation_between_shops(client, auth_headers, db_session, simple_product, category):
    from app.modules.identity.identity_model import Shop, User, UserRole
    from app.core.security import hash_password, create_access_token

    other_shop = Shop(name="Autre Boutique", status=__import__("app.modules.identity.identity_model", fromlist=["ShopStatus"]).ShopStatus.APPROVED)
    db_session.add(other_shop)
    db_session.commit()
    db_session.refresh(other_shop)
    other_cat = __import__("app.modules.categories.categories_model", fromlist=["Category"]).Category(shop_id=other_shop.id, name="AUTRE")
    db_session.add(other_cat)
    db_session.commit()
    db_session.refresh(other_cat)
    other_prod = __import__("app.modules.products.products_model", fromlist=["Product"]).Product(
        shop_id=other_shop.id, category_id=other_cat.id, name="AUTREPROD", unit_price=1000, quantity=0, unit="unite", is_transformable=False
    )
    db_session.add(other_prod)
    db_session.commit()
    db_session.refresh(other_prod)
    other_user = User(shop_id=other_shop.id, full_name="Other", email="other@test.com", hashed_password=hash_password("Test1234!"), role=UserRole.OWNER, is_active=True)
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)
    other_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(other_user.id), 'tv': other_user.token_version})}"}

    # owner sees their product pending
    pending_owner = client.get("/stock-initializations/pending", headers=auth_headers).json()["items"]
    assert any(i["product_id"] == simple_product.id for i in pending_owner)
    # other shop sees their product pending, not the first
    pending_other = client.get("/stock-initializations/pending", headers=other_headers).json()["items"]
    assert any(i["product_id"] == other_prod.id for i in pending_other)
    assert not any(i["product_id"] == simple_product.id for i in pending_other)


# ---- Concurrence ----
import threading

from fastapi.testclient import TestClient

from app.main import app


def test_concurrent_initialization_same_form_only_one_succeeds(client, auth_headers, db_session, simple_product):
    results = {}

    def _init(barrier, index):
        with TestClient(app) as local_client:
            barrier.wait(timeout=5)
            results[index] = local_client.post(
                "/stock-initializations",
                headers=auth_headers,
                json={"lines": [{"product_id": simple_product.id, "unit_target": "principale", "quantity": 7}]},
            )

    barrier = threading.Barrier(2)
    threads = [threading.Thread(target=_init, args=(barrier, i)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    statuses = sorted(r.status_code for r in results.values())
    assert statuses == [201, 400], statuses

    db_session.refresh(simple_product)
    assert simple_product.quantity == 17  # 10 + 7, incrémenté une seule fois

    movements = client.get("/stock-receipts/movements", headers=auth_headers).json()
    # Seul le mouvement de cette initialisation doit exister pour ce produit
    init_movs = [m for m in movements["items"] if m["product_id"] == simple_product.id and m["source_type"] == "stock_initialization"]
    assert len(init_movs) == 1
    assert init_movs[0]["quantity_delta"] == 7

    # Une seule initialisation enregistrée pour cette forme
    inits = client.get("/stock-initializations/pending", headers=auth_headers).json()["items"]
    assert not any(i["product_id"] == simple_product.id for i in inits)


def test_concurrent_initialization_different_forms_same_product_both_succeed_if_possible(client, auth_headers, db_session, transformable_product):
    results = {}

    def _init_princ(barrier, index):
        with TestClient(app) as local_client:
            barrier.wait(timeout=5)
            results[index] = local_client.post(
                "/stock-initializations",
                headers=auth_headers,
                json={"lines": [{"product_id": transformable_product.id, "unit_target": "principale", "quantity": 4}]},
            )

    def _init_sec(barrier, index):
        with TestClient(app) as local_client:
            barrier.wait(timeout=5)
            results[index] = local_client.post(
                "/stock-initializations",
                headers=auth_headers,
                json={"lines": [{"product_id": transformable_product.id, "unit_target": "secondaire", "quantity": 8}]},
            )

    barrier = threading.Barrier(2)
    threads = [
        threading.Thread(target=_init_princ, args=(barrier, 0)),
        threading.Thread(target=_init_sec, args=(barrier, 1)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    # Both should succeed as they target different forms
    assert all(r.status_code == 201 for r in results.values()), {i: (r.status_code, r.text) for i, r in results.items()}

    db_session.refresh(transformable_product)
    assert transformable_product.quantity == 7  # 3 + 4
    assert transformable_product.quantity_secondaire == 8

    movements = client.get("/stock-receipts/movements", headers=auth_headers).json()
    init_movs = [m for m in movements["items"] if m["product_id"] == transformable_product.id and m["source_type"] == "stock_initialization"]
    assert len(init_movs) == 2


def test_request_with_no_valid_quantity_creates_nothing(client, auth_headers, db_session, simple_product):
    start_qty = simple_product.quantity
    resp = _init_resp(client, auth_headers, [{"product_id": simple_product.id, "unit_target": "principale", "quantity": None}])
    assert resp.status_code == 400
    db_session.refresh(simple_product)
    assert simple_product.quantity == start_qty
    movements = client.get("/stock-receipts/movements", headers=auth_headers).json()
    assert not any(m["product_id"] == simple_product.id and m["source_type"] == "stock_initialization" for m in movements["items"])
    pending = client.get("/stock-initializations/pending", headers=auth_headers).json()["items"]
    assert any(i["product_id"] == simple_product.id for i in pending)

