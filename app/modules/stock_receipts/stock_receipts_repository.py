from datetime import datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from app.modules.stock_receipts.stock_receipts_model import StockMovement, StockReceipt, StockReceiptStatus


class StockReceiptRepository:
    def __init__(self, db: Session):
        self._db = db

    def _base_query(self):
        return self._db.query(StockReceipt).options(
            joinedload(StockReceipt.lines),
            joinedload(StockReceipt.supplier),
            joinedload(StockReceipt.created_by),
            joinedload(StockReceipt.validated_by),
        )

    def list_paginated(
        self,
        shop_id: int,
        page: int,
        page_size: int,
        status_filter: str | None,
        supplier_id: int | None,
        date: str | None,
    ):
        query = self._base_query().filter(StockReceipt.shop_id == shop_id)
        if status_filter:
            query = query.filter(StockReceipt.status == StockReceiptStatus(status_filter))
        if supplier_id is not None:
            query = query.filter(StockReceipt.supplier_id == supplier_id)
        if date:
            day_start = datetime.strptime(date, "%Y-%m-%d")
            day_end = day_start + timedelta(days=1)
            query = query.filter(StockReceipt.created_at >= day_start, StockReceipt.created_at < day_end)

        total = query.count()
        items = query.order_by(StockReceipt.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def get_by_id(self, shop_id: int, receipt_id: int) -> StockReceipt | None:
        return self._base_query().filter(StockReceipt.id == receipt_id, StockReceipt.shop_id == shop_id).first()

    def get_by_id_locked(self, shop_id: int, receipt_id: int) -> StockReceipt | None:
        # FOR UPDATE sur l'en-tête : empêche deux appels concurrents à
        # validate()/cancel() sur le même document (double clic, deux onglets).
        return (
            self._db.query(StockReceipt)
            .filter(StockReceipt.id == receipt_id, StockReceipt.shop_id == shop_id)
            .with_for_update()
            .first()
        )

    def save_new(self, receipt: StockReceipt) -> StockReceipt:
        self._db.add(receipt)
        self._db.commit()
        self._db.refresh(receipt)
        return receipt

    def save(self, receipt: StockReceipt) -> StockReceipt:
        self._db.commit()
        self._db.refresh(receipt)
        return receipt

    def delete(self, receipt: StockReceipt) -> None:
        self._db.delete(receipt)
        self._db.commit()

    def movements_list_paginated(self, shop_id: int, page: int, page_size: int, product_id: int | None):
        query = (
            self._db.query(StockMovement)
            .options(joinedload(StockMovement.created_by))
            .filter(StockMovement.shop_id == shop_id)
        )
        if product_id is not None:
            query = query.filter(StockMovement.product_id == product_id)
        total = query.count()
        items = query.order_by(StockMovement.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return items, total
