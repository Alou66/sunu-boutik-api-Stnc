"""Caractérise le module Approvisionnement : un StockReceipt en brouillon ne
touche pas le stock, sa validation crédite products.quantity/quantity_secondaire
et écrit un StockMovement par ligne, et son annulation les reprend (sauf si le
stock reçu a déjà été consommé entre-temps).
Réf. app/modules/stock_receipts/stock_receipts_service.py.
"""


def _create_receipt(client, auth_headers, lines, supplier_id=None):
    return client.post(
        "/stock-receipts",
        headers=auth_headers,
        json={"supplier_id": supplier_id, "reference": "BL-001", "note": None, "lines": lines},
    )


def test_create_draft_does_not_touch_stock(client, auth_headers, db_session, simple_product):
    resp = _create_receipt(
        client, auth_headers,
        [{"product_id": simple_product.id, "unit_target": "principale", "quantity": 5, "unit_cost": 1000}],
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "draft"
    assert body["total_cost"] == 5000

    db_session.refresh(simple_product)
    assert simple_product.quantity == 10  # inchangé tant que non validé


def test_validate_increments_principal_quantity_and_logs_movement(client, auth_headers, db_session, simple_product):
    created = _create_receipt(
        client, auth_headers,
        [{"product_id": simple_product.id, "unit_target": "principale", "quantity": 5, "unit_cost": 1000}],
    ).json()

    resp = client.post(f"/stock-receipts/{created['id']}/validate", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "validated"
    assert body["validated_at"] is not None

    db_session.refresh(simple_product)
    assert simple_product.quantity == 15  # 10 + 5

    movements = client.get("/stock-receipts/movements", headers=auth_headers).json()
    assert movements["total"] == 1
    assert movements["items"][0]["quantity_delta"] == 5
    assert movements["items"][0]["unit_target"] == "principale"


def test_validate_increments_secondary_quantity_for_transformable_product(client, auth_headers, db_session, transformable_product):
    created = _create_receipt(
        client, auth_headers,
        [{"product_id": transformable_product.id, "unit_target": "secondaire", "quantity": 6, "unit_cost": 2000}],
    ).json()

    resp = client.post(f"/stock-receipts/{created['id']}/validate", headers=auth_headers)
    assert resp.status_code == 200

    db_session.refresh(transformable_product)
    assert transformable_product.quantity == 3  # forme principale inchangée
    assert transformable_product.quantity_secondaire == 6


def test_secondary_unit_target_rejected_for_non_transformable_product(client, auth_headers, simple_product):
    resp = _create_receipt(
        client, auth_headers,
        [{"product_id": simple_product.id, "unit_target": "secondaire", "quantity": 1, "unit_cost": 100}],
    )
    assert resp.status_code == 400
    assert "n'est pas transformable" in resp.json()["detail"]


def test_two_lines_same_product_different_unit_target(client, auth_headers, db_session, transformable_product):
    created = _create_receipt(
        client, auth_headers,
        [
            {"product_id": transformable_product.id, "unit_target": "principale", "quantity": 2, "unit_cost": 8000},
            {"product_id": transformable_product.id, "unit_target": "secondaire", "quantity": 4, "unit_cost": 2500},
        ],
    ).json()
    assert len(created["lines"]) == 2

    client.post(f"/stock-receipts/{created['id']}/validate", headers=auth_headers)

    db_session.refresh(transformable_product)
    assert transformable_product.quantity == 5  # 3 + 2
    assert transformable_product.quantity_secondaire == 4  # 0 + 4


def test_cannot_modify_validated_receipt(client, auth_headers, simple_product):
    created = _create_receipt(
        client, auth_headers,
        [{"product_id": simple_product.id, "unit_target": "principale", "quantity": 5, "unit_cost": 1000}],
    ).json()
    client.post(f"/stock-receipts/{created['id']}/validate", headers=auth_headers)

    resp = client.patch(
        f"/stock-receipts/{created['id']}",
        headers=auth_headers,
        json={"lines": [{"product_id": simple_product.id, "unit_target": "principale", "quantity": 1, "unit_cost": 1000}]},
    )
    assert resp.status_code == 400
    assert "brouillon" in resp.json()["detail"]


def test_cancel_validated_receipt_reverts_stock(client, auth_headers, db_session, simple_product):
    created = _create_receipt(
        client, auth_headers,
        [{"product_id": simple_product.id, "unit_target": "principale", "quantity": 5, "unit_cost": 1000}],
    ).json()
    client.post(f"/stock-receipts/{created['id']}/validate", headers=auth_headers)

    resp = client.post(f"/stock-receipts/{created['id']}/cancel", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    db_session.refresh(simple_product)
    assert simple_product.quantity == 10  # revenu à la valeur de départ


def test_cancel_validated_receipt_blocked_when_stock_already_consumed(client, auth_headers, db_session, simple_product):
    created = _create_receipt(
        client, auth_headers,
        [{"product_id": simple_product.id, "unit_target": "principale", "quantity": 5, "unit_cost": 1000}],
    ).json()
    client.post(f"/stock-receipts/{created['id']}/validate", headers=auth_headers)

    # Le stock reçu (10 + 5 = 15) est presque entièrement vendu depuis.
    simple_product.quantity = 1
    db_session.commit()

    resp = client.post(f"/stock-receipts/{created['id']}/cancel", headers=auth_headers)
    assert resp.status_code == 400
    assert "Stock insuffisant" in resp.json()["detail"]


def test_product_quantity_not_editable_via_product_api(client, auth_headers, simple_product):
    resp = client.patch(
        f"/products/{simple_product.id}",
        headers=auth_headers,
        json={"quantity": 999},
    )
    assert resp.status_code == 200
    assert resp.json()["quantity"] == 10  # champ ignoré, pas dans ProductUpdate
