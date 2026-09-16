from sqlalchemy.orm import Session, joinedload

from app.modules.transformations.transformations_model import TransformationLog


class TransformationRepository:
    def __init__(self, db: Session):
        self._db = db

    def list_paginated(self, shop_id: int, page: int, page_size: int, product_id: int | None):
        query = (
            self._db.query(TransformationLog)
            .options(joinedload(TransformationLog.created_by))
            .filter(TransformationLog.shop_id == shop_id)
        )
        if product_id is not None:
            query = query.filter(TransformationLog.product_id == product_id)
        total = query.count()
        items = query.order_by(TransformationLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def save_new(self, log: TransformationLog) -> TransformationLog:
        self._db.add(log)
        self._db.commit()
        self._db.refresh(log)
        return log

    def find_by_idempotency_key(self, shop_id: int, idempotency_key: str) -> TransformationLog | None:
        return (
            self._db.query(TransformationLog)
            .filter(TransformationLog.shop_id == shop_id, TransformationLog.idempotency_key == idempotency_key)
            .first()
        )
