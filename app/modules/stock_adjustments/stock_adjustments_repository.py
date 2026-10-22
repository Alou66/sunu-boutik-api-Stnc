from sqlalchemy.orm import Session

from app.modules.stock_adjustments.stock_adjustments_model import StockAdjustment


class StockAdjustmentRepository:
    def __init__(self, db: Session):
        self._db = db

    def save_new(self, adjustment: StockAdjustment) -> StockAdjustment:
        self._db.add(adjustment)
        self._db.flush()
        return adjustment
