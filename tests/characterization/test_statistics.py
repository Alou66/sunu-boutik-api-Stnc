"""Caractérise le module Statistiques : vue d'ensemble du stock actuel (capital
investi, marge latente), ventes/achats sur une période filtrée, bénéfice réel
capturé via InvoiceLine.cost_price (avec fallback sur purchase_price actuel
pour l'historique pré-migration), articles dormants et scoping multi-boutique.
Réf. app/modules/statistics/.
"""
from datetime import datetime, timedelta

from app.modules.billing.billing_model import Invoice, InvoiceLine
from app.modules.identity.identity_model import Shop, ShopStatus, User, UserRole
from app.modules.products.products_model import Product
from app.core.security import create_access_token, hash_password


def _period(days_back=0, days_forward=0):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    date_from = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    date_to = (datetime.utcnow() + timedelta(days=days_forward)).strftime("%Y-%m-%d")
    return date_from, date_to


def _create_invoice(client, auth_headers, product_id, quantity=1):
    resp = client.post(
        "/invoices",
        headers=auth_headers,
        json={"lines": [{"product_id": product_id, "quantity": quantity}]},
    )
    assert resp.status_code == 201
    return resp.json()


def test_stock_overview_computes_invested_capital_and_latent_margin(client, auth_headers, db_session, shop, category):
    p1 = Product(shop_id=shop.id, category_id=category.id, name="Sucre", purchase_price=800, unit_price=1000, quantity=10)
    p2 = Product(shop_id=shop.id, category_id=category.id, name="Huile", purchase_price=0, unit_price=0, quantity=0)
    db_session.add_all([p1, p2])
    db_session.commit()

    date_from, date_to = _period(days_back=1)
    resp = client.get(f"/statistics?date_from={date_from}&date_to={date_to}", headers=auth_headers)
    assert resp.status_code == 200
    stock = resp.json()["stock"]

    assert stock["total_products"] == 2
    assert stock["invested_capital"] == 8000  # 800 * 10 + 0 * 0
    assert stock["potential_sale_value"] == 10000  # 1000 * 10
    assert stock["latent_margin"] == 2000
    assert stock["out_of_stock_count"] == 1  # p2 (quantity=0)
    assert stock["low_stock_count"] == 1  # p2 (quantity < 5)


def test_sales_period_tracks_invoiced_collected_and_pending(client, auth_headers, db_session, shop, category):
    product = Product(shop_id=shop.id, category_id=category.id, name="Riz", purchase_price=10000, unit_price=15000, quantity=10)
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    invoice = _create_invoice(client, auth_headers, product.id, quantity=2)
    client.post(f"/invoices/{invoice['id']}/payments", headers=auth_headers, json={"amount": 10000})

    date_from, date_to = _period(days_back=1)
    resp = client.get(f"/statistics?date_from={date_from}&date_to={date_to}", headers=auth_headers)
    sales = resp.json()["sales"]

    assert sales["invoiced_total"] == 30000
    assert sales["collected_total"] == 10000
    assert sales["pending_total"] == 20000
    assert sales["invoices_count"] == 1


def test_cost_price_captured_automatically_and_drives_real_profit(client, auth_headers, db_session, shop, category):
    product = Product(shop_id=shop.id, category_id=category.id, name="Riz", purchase_price=10000, unit_price=15000, quantity=10)
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    _create_invoice(client, auth_headers, product.id, quantity=2)

    line = db_session.query(InvoiceLine).filter(InvoiceLine.product_id == product.id).one()
    assert line.cost_price == 10000

    date_from, date_to = _period(days_back=1)
    resp = client.get(f"/statistics?date_from={date_from}&date_to={date_to}", headers=auth_headers)
    sales = resp.json()["sales"]

    assert sales["real_profit"] == 10000  # (15000-10000) * 2
    assert round(sales["margin_rate"], 2) == round(10000 / 30000 * 100, 2)


def test_real_profit_falls_back_to_current_purchase_price_for_legacy_lines_without_cost_price(
    client, auth_headers, db_session, shop, category
):
    product = Product(shop_id=shop.id, category_id=category.id, name="Riz", purchase_price=10000, unit_price=15000, quantity=10)
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    invoice = Invoice(shop_id=shop.id, number="FA-LEGACY-0001", total=30000, amount_paid=0)
    db_session.add(invoice)
    db_session.commit()
    db_session.refresh(invoice)
    legacy_line = InvoiceLine(
        invoice_id=invoice.id,
        product_id=product.id,
        product_name=product.name,
        quantity=2,
        unit_price=15000,
        line_total=30000,
        cost_price=None,  # simule une ligne créée avant l'introduction du champ
    )
    db_session.add(legacy_line)
    db_session.commit()

    date_from, date_to = _period(days_back=1)
    resp = client.get(f"/statistics?date_from={date_from}&date_to={date_to}", headers=auth_headers)
    sales = resp.json()["sales"]

    assert sales["real_profit"] == 10000  # fallback sur product.purchase_price actuel (10000)


def test_purchases_period_aggregates_validated_receipts(client, auth_headers, db_session, shop, category):
    product = Product(shop_id=shop.id, category_id=category.id, name="Riz", purchase_price=10000, unit_price=15000, quantity=10)
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    supplier_resp = client.post("/suppliers", headers=auth_headers, json={"name": "Grossiste Dakar"})
    assert supplier_resp.status_code == 201
    supplier_id = supplier_resp.json()["id"]

    receipt = client.post(
        "/stock-receipts",
        headers=auth_headers,
        json={
            "supplier_id": supplier_id,
            "reference": "BL-001",
            "note": None,
            "lines": [{"product_id": product.id, "unit_target": "principale", "quantity": 5, "unit_cost": 9000}],
        },
    ).json()
    client.post(f"/stock-receipts/{receipt['id']}/validate", headers=auth_headers)

    date_from, date_to = _period(days_back=1)
    resp = client.get(f"/statistics?date_from={date_from}&date_to={date_to}", headers=auth_headers)
    purchases = resp.json()["purchases"]

    assert purchases["total_spent"] == 45000
    assert purchases["receipts_count"] == 1


def test_purchases_period_ignores_draft_receipts(client, auth_headers, db_session, shop, category):
    product = Product(shop_id=shop.id, category_id=category.id, name="Riz", purchase_price=10000, unit_price=15000, quantity=10)
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    client.post(
        "/stock-receipts",
        headers=auth_headers,
        json={
            "supplier_id": None,
            "reference": "BL-002",
            "note": None,
            "lines": [{"product_id": product.id, "unit_target": "principale", "quantity": 5, "unit_cost": 9000}],
        },
    )

    date_from, date_to = _period(days_back=1)
    resp = client.get(f"/statistics?date_from={date_from}&date_to={date_to}", headers=auth_headers)
    purchases = resp.json()["purchases"]

    assert purchases["total_spent"] == 0
    assert purchases["receipts_count"] == 0


def test_dormant_products_lists_never_sold_and_old_sales_but_not_recent(client, auth_headers, db_session, shop, category):
    never_sold = Product(shop_id=shop.id, category_id=category.id, name="Jamais vendu", purchase_price=1000, unit_price=1500, quantity=5)
    sold_long_ago = Product(shop_id=shop.id, category_id=category.id, name="Vendu il y a longtemps", purchase_price=1000, unit_price=1500, quantity=5)
    sold_recently = Product(shop_id=shop.id, category_id=category.id, name="Vendu récemment", purchase_price=1000, unit_price=1500, quantity=5)
    db_session.add_all([never_sold, sold_long_ago, sold_recently])
    db_session.commit()
    for p in (sold_long_ago, sold_recently):
        db_session.refresh(p)

    _create_invoice(client, auth_headers, sold_long_ago.id, quantity=1)
    old_invoice = db_session.query(Invoice).filter(Invoice.shop_id == shop.id).order_by(Invoice.id.desc()).first()
    old_invoice.created_at = datetime.utcnow() - timedelta(days=45)
    db_session.commit()

    _create_invoice(client, auth_headers, sold_recently.id, quantity=1)

    date_from, date_to = _period(days_back=1)
    resp = client.get(f"/statistics?date_from={date_from}&date_to={date_to}", headers=auth_headers)
    dormant_ids = {item["product_id"] for item in resp.json()["rankings"]["dormant_products"]}

    assert never_sold.id in dormant_ids
    assert sold_long_ago.id in dormant_ids
    assert sold_recently.id not in dormant_ids


def test_date_to_before_date_from_returns_400(client, auth_headers):
    resp = client.get("/statistics?date_from=2026-09-10&date_to=2026-09-01", headers=auth_headers)
    assert resp.status_code == 400


def test_statistics_are_scoped_to_current_shop(client, auth_headers, db_session, shop, category, simple_product):
    other_shop = Shop(name="Autre boutique", status=ShopStatus.APPROVED)
    db_session.add(other_shop)
    db_session.commit()
    db_session.refresh(other_shop)
    other_owner = User(
        shop_id=other_shop.id,
        full_name="Autre proprietaire",
        email="other-owner@example.com",
        hashed_password=hash_password("Test1234!"),
        role=UserRole.OWNER,
        is_active=True,
    )
    db_session.add(other_owner)
    db_session.commit()
    db_session.refresh(other_owner)
    other_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(other_owner.id)})}"}

    other_product = Product(shop_id=other_shop.id, category_id=category.id, name="Article autre boutique", purchase_price=5000, unit_price=8000, quantity=50)
    db_session.add(other_product)
    db_session.commit()

    date_from, date_to = _period(days_back=1)
    resp = client.get(f"/statistics?date_from={date_from}&date_to={date_to}", headers=other_headers)
    stock = resp.json()["stock"]

    assert stock["total_products"] == 1
    assert stock["invested_capital"] == 5000 * 50
