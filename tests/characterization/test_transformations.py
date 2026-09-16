"""Caractérise la transformation de stock entre forme principale et forme
secondaire d'un article transformable, et le blocage de désactivation tant
qu'un reliquat existe en forme secondaire.
Réf. app/routers/transformations.py, app/routers/products.py::update_product.
"""


def test_transform_to_secondaire_applies_conversion_ratio(client, auth_headers, transformable_product):
    resp = client.post(
        "/transformations/execute",
        headers=auth_headers,
        json={"product_id": transformable_product.id, "direction": "to_secondaire", "quantity": 1},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["log"]["quantity_from"] == 1
    assert body["log"]["quantity_to"] == 4  # conversion_ratio = 4
    assert body["product"]["quantity"] == 2
    assert body["product"]["quantity_secondaire"] == 4


def test_transform_to_principale_applies_inverse_ratio(client, auth_headers, db_session, transformable_product):
    transformable_product.quantity_secondaire = 8
    db_session.commit()

    resp = client.post(
        "/transformations/execute",
        headers=auth_headers,
        json={"product_id": transformable_product.id, "direction": "to_principale", "quantity": 8},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["log"]["quantity_to"] == 2  # 8 / conversion_ratio(4)
    assert body["product"]["quantity"] == 5  # 3 + 2
    assert body["product"]["quantity_secondaire"] == 0


def test_transform_insufficient_stock_returns_400(client, auth_headers, transformable_product):
    resp = client.post(
        "/transformations/execute",
        headers=auth_headers,
        json={"product_id": transformable_product.id, "direction": "to_secondaire", "quantity": 999},
    )
    assert resp.status_code == 400
    assert "Stock insuffisant" in resp.json()["detail"]


def test_transform_idempotency_key_replayed_returns_same_log(client, auth_headers, transformable_product):
    payload = {
        "product_id": transformable_product.id,
        "direction": "to_secondaire",
        "quantity": 1,
        "idempotency_key": "retry-key-transfo-1",
    }

    first = client.post("/transformations/execute", headers=auth_headers, json=payload)
    second = client.post("/transformations/execute", headers=auth_headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["log"]["id"] == second.json()["log"]["id"]

    history = client.get("/transformations/history", headers=auth_headers).json()
    assert history["total"] == 1

    product = client.get(f"/products/{transformable_product.id}", headers=auth_headers).json()
    assert product["quantity"] == 2  # décrémenté une seule fois malgré les deux requêtes
    assert product["quantity_secondaire"] == 4


def test_transform_non_transformable_product_returns_400(client, auth_headers, simple_product):
    resp = client.post(
        "/transformations/execute",
        headers=auth_headers,
        json={"product_id": simple_product.id, "direction": "to_secondaire", "quantity": 1},
    )
    assert resp.status_code == 400
    assert "n'est pas transformable" in resp.json()["detail"]


def test_deactivate_transformable_blocked_while_secondary_stock_remains(client, auth_headers, db_session, transformable_product):
    transformable_product.quantity_secondaire = 2
    db_session.commit()

    resp = client.patch(
        f"/products/{transformable_product.id}",
        headers=auth_headers,
        json={"is_transformable": False},
    )
    assert resp.status_code == 400
    assert "Transformez-les d'abord" in resp.json()["detail"]


def test_deactivate_transformable_allowed_once_secondary_stock_is_zero(client, auth_headers, transformable_product):
    resp = client.patch(
        f"/products/{transformable_product.id}",
        headers=auth_headers,
        json={"is_transformable": False},
    )
    assert resp.status_code == 200
    assert resp.json()["is_transformable"] is False
