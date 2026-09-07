from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.modules.bon_client.bon_client_model import BonClient


class BonClientRepository:
    def __init__(self, db: Session):
        self._db = db

    def list_paginated(self, shop_id: int, page: int, page_size: int, search: str | None) -> tuple[list[BonClient], int]:
        query = self._db.query(BonClient).filter(BonClient.shop_id == shop_id)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    BonClient.title.ilike(pattern),
                    BonClient.content.ilike(pattern),
                    func.to_char(BonClient.created_at, "DD/MM/YYYY").ilike(pattern),
                    func.to_char(BonClient.created_at, "YYYY-MM-DD").ilike(pattern),
                )
            )
        total = query.count()
        items = query.order_by(BonClient.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def get_by_id(self, shop_id: int, bon_client_id: int) -> BonClient | None:
        return self._db.query(BonClient).filter(BonClient.id == bon_client_id, BonClient.shop_id == shop_id).first()

    def save_new(self, bon_client: BonClient) -> BonClient:
        self._db.add(bon_client)
        self._db.commit()
        self._db.refresh(bon_client)
        return bon_client

    def save(self, bon_client: BonClient) -> BonClient:
        self._db.commit()
        self._db.refresh(bon_client)
        return bon_client

    def delete(self, bon_client: BonClient) -> None:
        self._db.delete(bon_client)
        self._db.commit()
