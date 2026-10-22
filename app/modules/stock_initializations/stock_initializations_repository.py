from sqlalchemy.orm import Session, joinedload

from app.modules.stock_initializations.stock_initializations_model import StockInitialization, StockInitializationLine


class StockInitializationRepository:
    def __init__(self, db: Session):
        self._db = db

    def save_new(self, initialization: StockInitialization) -> StockInitialization:
        self._db.add(initialization)
        self._db.flush()
        return initialization

    def has_initialization_for_form(self, shop_id: int, product_id: int, unit_target: str) -> bool:
        return (
            self._db.query(StockInitializationLine)
            .filter(
                StockInitializationLine.shop_id == shop_id,
                StockInitializationLine.product_id == product_id,
                StockInitializationLine.unit_target == unit_target,
            )
            .first()
            is not None
        )

    def get_by_id(self, shop_id: int, initialization_id: int) -> StockInitialization | None:
        return (
            self._db.query(StockInitialization)
            .options(joinedload(StockInitialization.lines))
            .filter(StockInitialization.id == initialization_id, StockInitialization.shop_id == shop_id)
            .first()
        )
