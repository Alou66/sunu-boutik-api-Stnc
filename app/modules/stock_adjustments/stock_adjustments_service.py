from sqlalchemy.orm import Session

from app.modules.products.products_repository import ProductRepository
from app.modules.stock_adjustments.stock_adjustments_model import StockAdjustment
from app.modules.stock_adjustments.stock_adjustments_repository import StockAdjustmentRepository
from app.modules.stock_receipts.stock_receipts_model import StockMovement


class StockAdjustmentError(Exception):
    pass


class StockAdjustmentValidationError(Exception):
    pass


class StockAdjustmentService:
    def __init__(self, db: Session):
        self._db = db
        self._repo = StockAdjustmentRepository(db)
        self._products = ProductRepository(db)

    def create(self, shop_id: int, user_id: int, data: dict) -> StockAdjustment:
        product_id = int(data["product_id"])
        unit_target = data["unit_target"]
        adjustment_type = data["adjustment_type"]
        quantity = float(data["quantity"])
        reason = str(data.get("reason") or "").strip()

        if adjustment_type not in ("entry", "exit"):
            raise StockAdjustmentValidationError("Type d'ajustement invalide")
        if quantity <= 0:
            raise StockAdjustmentValidationError("La quantité doit être strictement positive")
        if not reason:
            raise StockAdjustmentValidationError("Le motif est obligatoire")

        product = self._products.get_by_id_locked(shop_id, product_id)
        if not product:
            raise StockAdjustmentValidationError("Produit introuvable")

        if unit_target not in ("principale", "secondaire"):
            raise StockAdjustmentValidationError("Forme invalide")
        if unit_target == "secondaire":
            if not product.is_transformable or not product.unit_secondaire:
                raise StockAdjustmentValidationError("Forme secondaire incompatible avec ce produit")
            stock_before = float(product.quantity_secondaire or 0)
        else:
            stock_before = float(product.quantity or 0)

        if adjustment_type == "entry":
            quantity_delta = quantity
        else:
            if stock_before < quantity:
                raise StockAdjustmentValidationError("Stock insuffisant pour cette sortie")
            quantity_delta = -quantity

        stock_after = stock_before + quantity_delta

        if unit_target == "secondaire":
            product.quantity_secondaire = stock_after
        else:
            product.quantity = stock_after

        adjustment = StockAdjustment(
            shop_id=shop_id,
            product_id=product.id,
            product_name=product.name,
            unit_target=unit_target,
            adjustment_type=adjustment_type,
            quantity=quantity,
            quantity_delta=quantity_delta,
            stock_before=stock_before,
            stock_after=stock_after,
            reason=reason,
            created_by_id=user_id,
        )
        self._repo.save_new(adjustment)

        self._db.add(
            StockMovement(
                shop_id=shop_id,
                product_id=product.id,
                product_name=product.name,
                source_type="stock_adjustment",
                source_id=adjustment.id,
                unit_target=unit_target,
                quantity_delta=quantity_delta,
                created_by_id=user_id,
            )
        )

        try:
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        self._db.refresh(adjustment)
        return adjustment
