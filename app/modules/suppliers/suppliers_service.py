from sqlalchemy.orm import Session

from app.modules.suppliers.suppliers_model import Supplier
from app.modules.suppliers.suppliers_repository import SupplierRepository


class SupplierNotFoundError(Exception):
    pass


class SupplierValidationError(Exception):
    pass


class SupplierInUseError(Exception):
    pass


class SupplierService:
    def __init__(self, db: Session):
        self._db = db
        self._repo = SupplierRepository(db)

    def list(self, shop_id: int, page: int, page_size: int, search: str | None) -> tuple[list[Supplier], int]:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        return self._repo.list_paginated(shop_id, page, page_size, search)

    def get(self, shop_id: int, supplier_id: int) -> Supplier:
        supplier = self._repo.get_by_id(shop_id, supplier_id)
        if not supplier:
            raise SupplierNotFoundError("Fournisseur introuvable")
        return supplier

    def create(self, shop_id: int, data: dict) -> Supplier:
        if not data["name"]:
            raise SupplierValidationError("Le nom du fournisseur est requis")
        supplier = Supplier(shop_id=shop_id, **data)
        return self._repo.save_new(supplier)

    def update(self, shop_id: int, supplier_id: int, data: dict) -> Supplier:
        supplier = self.get(shop_id, supplier_id)
        if "name" in data and not data["name"]:
            raise SupplierValidationError("Le nom du fournisseur est requis")
        for field, value in data.items():
            setattr(supplier, field, value)
        return self._repo.save(supplier)

    def delete(self, shop_id: int, supplier_id: int) -> None:
        from app.modules.stock_receipts.stock_receipts_model import StockReceipt

        supplier = self.get(shop_id, supplier_id)
        if self._db.query(StockReceipt).filter(StockReceipt.supplier_id == supplier_id).first():
            raise SupplierInUseError("Impossible de supprimer : ce fournisseur a des approvisionnements associés")
        self._repo.delete(supplier)
