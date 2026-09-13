from datetime import datetime, timedelta

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.modules.billing.billing_model import Invoice, InvoiceLine
from app.modules.payments.payments_model import Payment
from app.modules.products.products_model import Product
from app.modules.stock_receipts.stock_receipts_model import StockReceipt, StockReceiptStatus

# Seuils fixes v1 (non configurables, voir décision produit) : un article est
# "stock bas" en dessous de cette quantité, "dormant" s'il n'a été vendu par
# aucune ligne de facture depuis ce nombre de jours.
LOW_STOCK_THRESHOLD = 5
DORMANT_DAYS = 30


class StatisticsRepository:
    def __init__(self, db: Session):
        self._db = db

    # ---- Bloc stock actuel (photo instantanée, pas de filtre période) ----

    def stock_overview(self, shop_id: int) -> dict:
        base = self._db.query(Product).filter(Product.shop_id == shop_id)
        total_products = base.count()
        out_of_stock_count = base.filter(Product.quantity <= 0).count()
        low_stock_count = base.filter(Product.quantity < LOW_STOCK_THRESHOLD).count()

        invested_capital, potential_sale_value = (
            self._db.query(
                func.coalesce(func.sum(Product.purchase_price * Product.quantity), 0),
                func.coalesce(func.sum(Product.unit_price * Product.quantity), 0),
            )
            .filter(Product.shop_id == shop_id)
            .one()
        )
        invested_capital = float(invested_capital or 0)
        potential_sale_value = float(potential_sale_value or 0)
        return {
            "total_products": total_products,
            "invested_capital": invested_capital,
            "potential_sale_value": potential_sale_value,
            "latent_margin": potential_sale_value - invested_capital,
            "out_of_stock_count": out_of_stock_count,
            "low_stock_count": low_stock_count,
        }

    # ---- Expression coût effectif réutilisée par tous les agrégats "période" ----

    def _effective_cost_price(self):
        # COALESCE(coût capturé à la vente, coût d'achat ACTUEL du produit
        # selon la forme vendue, 0) : couvre les lignes historiques (cost_price
        # NULL, créées avant l'introduction du champ) et le cas où
        # purchase_price_secondaire n'a jamais été renseigné.
        fallback = case(
            (InvoiceLine.form == "secondaire", Product.purchase_price_secondaire),
            else_=Product.purchase_price,
        )
        return func.coalesce(InvoiceLine.cost_price, fallback, 0)

    # ---- Bloc ventes de la période ----

    def sales_period(self, shop_id: int, start: datetime, end: datetime) -> dict:
        invoiced_total, invoices_count = (
            self._db.query(func.coalesce(func.sum(Invoice.total), 0), func.count(Invoice.id))
            .filter(Invoice.shop_id == shop_id, Invoice.created_at >= start, Invoice.created_at < end)
            .one()
        )

        # Comme cashier_service.get_daily_summary : l'encaissement compte le
        # jour où le paiement a été reçu (Payment.created_at), pas la date de
        # la facture, pour rester cohérent avec le journal de caisse.
        collected_total = (
            self._db.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(
                Payment.shop_id == shop_id,
                Payment.created_at >= start,
                Payment.created_at < end,
                Payment.voided_at.is_(None),
            )
            .scalar()
        )

        cost_expr = self._effective_cost_price()
        real_profit = (
            self._db.query(
                func.coalesce(func.sum((InvoiceLine.unit_price - cost_expr) * InvoiceLine.quantity), 0)
            )
            .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
            .join(Product, Product.id == InvoiceLine.product_id)
            .filter(Invoice.shop_id == shop_id, Invoice.created_at >= start, Invoice.created_at < end)
            .scalar()
        )

        return {
            "invoiced_total": float(invoiced_total or 0),
            "collected_total": float(collected_total or 0),
            "real_profit": float(real_profit or 0),
            "invoices_count": invoices_count,
        }

    # ---- Bloc achats de la période ----

    def purchases_period(self, shop_id: int, start: datetime, end: datetime) -> dict:
        total_spent, receipts_count = (
            self._db.query(func.coalesce(func.sum(StockReceipt.total_cost), 0), func.count(StockReceipt.id))
            .filter(
                StockReceipt.shop_id == shop_id,
                StockReceipt.status == StockReceiptStatus.VALIDATED,
                StockReceipt.created_at >= start,
                StockReceipt.created_at < end,
            )
            .one()
        )

        return {
            "total_spent": float(total_spent or 0),
            "receipts_count": receipts_count,
        }

    # ---- Bloc classements (sur la période) ----

    def rankings(self, shop_id: int) -> dict:
        dormant_cutoff = datetime.utcnow() - timedelta(days=DORMANT_DAYS)
        last_sale_subq = (
            self._db.query(InvoiceLine.product_id, func.max(Invoice.created_at).label("last_sale_at"))
            .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
            .filter(Invoice.shop_id == shop_id)
            .group_by(InvoiceLine.product_id)
            .subquery()
        )
        dormant_rows = (
            self._db.query(Product.id, Product.name, Product.quantity, last_sale_subq.c.last_sale_at)
            .outerjoin(last_sale_subq, last_sale_subq.c.product_id == Product.id)
            .filter(
                Product.shop_id == shop_id,
                (last_sale_subq.c.last_sale_at.is_(None)) | (last_sale_subq.c.last_sale_at < dormant_cutoff),
            )
            .order_by(Product.name)
            .all()
        )
        dormant_products = [
            {
                "product_id": pid,
                "product_name": name,
                "quantity": float(qty or 0),
                "last_sale_at": last_sale_at.isoformat() if last_sale_at else None,
            }
            for pid, name, qty, last_sale_at in dormant_rows
        ]

        return {
            "dormant_products": dormant_products,
        }
