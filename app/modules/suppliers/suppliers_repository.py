from sqlalchemy.orm import Session

from app.modules.suppliers.suppliers_model import Supplier


class SupplierRepository:
    def __init__(self, db: Session):
        self._db = db

    def list_paginated(self, shop_id: int, page: int, page_size: int, search: str | None) -> tuple[list[Supplier], int]:
        query = self._db.query(Supplier).filter(Supplier.shop_id == shop_id)
        if search:
            query = query.filter(Supplier.name.ilike(f"%{search}%"))
        total = query.count()
        items = query.order_by(Supplier.name).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def get_by_id(self, shop_id: int, supplier_id: int) -> Supplier | None:
        return self._db.query(Supplier).filter(Supplier.id == supplier_id, Supplier.shop_id == shop_id).first()

    def save_new(self, supplier: Supplier) -> Supplier:
        self._db.add(supplier)
        self._db.commit()
        self._db.refresh(supplier)
        return supplier

    def save(self, supplier: Supplier) -> Supplier:
        self._db.commit()
        self._db.refresh(supplier)
        return supplier

    def delete(self, supplier: Supplier) -> None:
        self._db.delete(supplier)
        self._db.commit()
