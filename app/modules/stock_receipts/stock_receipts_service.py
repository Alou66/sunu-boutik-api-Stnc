from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.products.products_repository import ProductRepository
from app.modules.stock_receipts.stock_receipts_model import (
    StockMovement,
    StockReceipt,
    StockReceiptLine,
    StockReceiptStatus,
)
from app.modules.stock_receipts.stock_receipts_repository import StockReceiptRepository
from app.modules.suppliers.suppliers_repository import SupplierRepository


class StockReceiptNotFoundError(Exception):
    pass


class StockReceiptValidationError(Exception):
    pass


class StockReceiptLineProductNotFoundError(Exception):
    pass


class SupplierNotFoundError(Exception):
    pass


class StockReceiptLockedError(Exception):
    pass


class InsufficientStockError(Exception):
    pass


class StockReceiptService:
    def __init__(self, db: Session):
        self._db = db
        self._repo = StockReceiptRepository(db)
        self._products = ProductRepository(db)
        self._suppliers = SupplierRepository(db)

    # ---- Lecture ----

    def list(self, shop_id: int, page: int, page_size: int, status_filter: str | None, supplier_id: int | None, date: str | None):
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        if status_filter:
            try:
                StockReceiptStatus(status_filter)
            except ValueError:
                raise StockReceiptValidationError("Statut invalide")
        if date:
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise StockReceiptValidationError("Date invalide, format attendu AAAA-MM-JJ")
        return self._repo.list_paginated(shop_id, page, page_size, status_filter, supplier_id, date)

    def get(self, shop_id: int, receipt_id: int) -> StockReceipt:
        receipt = self._repo.get_by_id(shop_id, receipt_id)
        if not receipt:
            raise StockReceiptNotFoundError("Approvisionnement introuvable")
        return receipt

    def list_movements(self, shop_id: int, page: int, page_size: int, product_id: int | None):
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        return self._repo.movements_list_paginated(shop_id, page, page_size, product_id)

    # ---- Construction des lignes (partagée create/update) ----

    def _build_lines(self, shop_id: int, lines_payload: list) -> tuple[list[StockReceiptLine], float]:
        if not lines_payload:
            raise StockReceiptValidationError("L'approvisionnement doit contenir au moins un article")

        lines = []
        total_cost = 0.0
        for line in lines_payload:
            product_id = line["product_id"]
            unit_target = line["unit_target"]
            quantity = line["quantity"]
            unit_cost_override = line.get("unit_cost")

            product = self._products.get_by_id(shop_id, product_id)
            if not product:
                raise StockReceiptLineProductNotFoundError(f"Article {product_id} introuvable")
            if unit_target == "secondaire" and not product.is_transformable:
                raise StockReceiptValidationError(
                    f"{product.name} n'est pas transformable : impossible de l'approvisionner en forme secondaire"
                )
            default_cost = (
                product.purchase_price_secondaire if unit_target == "secondaire" else product.purchase_price
            ) or 0
            unit_cost = unit_cost_override if unit_cost_override is not None else default_cost
            total_cost += unit_cost * quantity
            lines.append(
                StockReceiptLine(
                    product_id=product.id,
                    product_name=product.name,
                    unit_target=unit_target,
                    quantity=quantity,
                    unit_cost=unit_cost,
                )
            )
        return lines, total_cost

    # ---- Écriture (brouillon) ----

    def create(self, shop_id: int, user_id: int, data: dict) -> StockReceipt:
        supplier_id = data.get("supplier_id")
        if supplier_id is not None and not self._suppliers.get_by_id(shop_id, supplier_id):
            raise SupplierNotFoundError("Fournisseur introuvable")

        lines, total_cost = self._build_lines(shop_id, data["lines"])

        receipt = StockReceipt(
            shop_id=shop_id,
            supplier_id=supplier_id,
            reference=data.get("reference"),
            note=data.get("note"),
            status=StockReceiptStatus.DRAFT,
            total_cost=total_cost,
            created_by_id=user_id,
        )
        receipt.lines = lines
        return self._repo.save_new(receipt)

    def update(self, shop_id: int, receipt_id: int, data: dict) -> StockReceipt:
        receipt = self.get(shop_id, receipt_id)
        if receipt.status != StockReceiptStatus.DRAFT:
            raise StockReceiptLockedError("Seul un approvisionnement en brouillon peut être modifié")

        supplier_id = data.get("supplier_id")
        if supplier_id is not None and not self._suppliers.get_by_id(shop_id, supplier_id):
            raise SupplierNotFoundError("Fournisseur introuvable")

        lines, total_cost = self._build_lines(shop_id, data["lines"])

        receipt.supplier_id = supplier_id
        receipt.reference = data.get("reference")
        receipt.note = data.get("note")
        receipt.total_cost = total_cost
        receipt.lines = lines
        return self._repo.save(receipt)

    def delete(self, shop_id: int, receipt_id: int) -> None:
        receipt = self.get(shop_id, receipt_id)
        if receipt.status != StockReceiptStatus.DRAFT:
            raise StockReceiptLockedError("Seul un approvisionnement en brouillon peut être supprimé")
        self._repo.delete(receipt)

    # ---- Validation / annulation ----

    def validate(self, shop_id: int, receipt_id: int, user_id: int) -> StockReceipt:
        receipt = self._repo.get_by_id_locked(shop_id, receipt_id)
        if not receipt:
            raise StockReceiptNotFoundError("Approvisionnement introuvable")
        if receipt.status != StockReceiptStatus.DRAFT:
            raise StockReceiptLockedError("Cet approvisionnement a déjà été validé ou annulé")

        # Verrouille les produits toujours dans le même ordre (product_id
        # croissant) pour éviter un deadlock si deux approvisionnements
        # partageant des articles sont validés en parallèle.
        for line in sorted(receipt.lines, key=lambda l: l.product_id):
            product = self._products.get_by_id_locked(shop_id, line.product_id)
            if not product:
                raise StockReceiptLineProductNotFoundError(f"Article {line.product_id} introuvable")
            if line.unit_target == "secondaire":
                product.quantity_secondaire += line.quantity
            else:
                product.quantity += line.quantity
            self._db.add(StockMovement(
                shop_id=shop_id,
                product_id=product.id,
                product_name=product.name,
                source_type="receipt",
                source_id=receipt.id,
                unit_target=line.unit_target,
                quantity_delta=line.quantity,
                created_by_id=user_id,
            ))

        receipt.status = StockReceiptStatus.VALIDATED
        receipt.validated_by_id = user_id
        receipt.validated_at = datetime.utcnow()
        self._db.commit()
        self._db.refresh(receipt)
        return receipt

    def cancel(self, shop_id: int, receipt_id: int, user_id: int) -> StockReceipt:
        receipt = self._repo.get_by_id_locked(shop_id, receipt_id)
        if not receipt:
            raise StockReceiptNotFoundError("Approvisionnement introuvable")
        if receipt.status == StockReceiptStatus.CANCELLED:
            raise StockReceiptLockedError("Cet approvisionnement est déjà annulé")

        if receipt.status == StockReceiptStatus.VALIDATED:
            for line in sorted(receipt.lines, key=lambda l: l.product_id):
                product = self._products.get_by_id_locked(shop_id, line.product_id)
                if not product:
                    raise StockReceiptLineProductNotFoundError(f"Article {line.product_id} introuvable")
                available = product.quantity_secondaire if line.unit_target == "secondaire" else product.quantity
                if available < line.quantity:
                    raise InsufficientStockError(
                        f"Stock insuffisant pour annuler la ligne {product.name} "
                        f"(déjà vendu ou transformé depuis la réception)"
                    )
                if line.unit_target == "secondaire":
                    product.quantity_secondaire -= line.quantity
                else:
                    product.quantity -= line.quantity
                self._db.add(StockMovement(
                    shop_id=shop_id,
                    product_id=product.id,
                    product_name=product.name,
                    source_type="receipt",
                    source_id=receipt.id,
                    unit_target=line.unit_target,
                    quantity_delta=-line.quantity,
                    created_by_id=user_id,
                ))

        receipt.status = StockReceiptStatus.CANCELLED
        self._db.commit()
        self._db.refresh(receipt)
        return receipt
