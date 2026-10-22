from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from app.modules.categories.categories_model import Category
from app.modules.products.products_model import Product
from app.modules.products.products_repository import ProductRepository
from app.modules.stock_initializations.stock_initializations_model import StockInitialization, StockInitializationLine
from app.modules.stock_initializations.stock_initializations_repository import StockInitializationRepository
from app.modules.stock_receipts.stock_receipts_model import StockReceipt, StockReceiptLine, StockReceiptStatus
from app.modules.stock_receipts.stock_receipts_model import StockMovement


class StockInitializationError(Exception):
    pass


class StockInitializationValidationError(Exception):
    pass


class StockInitializationService:
    def __init__(self, db: Session):
        self._db = db
        self._repo = StockInitializationRepository(db)
        self._products = ProductRepository(db)

    def list_pending(self, shop_id: int) -> List[dict]:
        # Forms already initialized
        initialized_forms = (
            self._db.query(StockInitializationLine.product_id, StockInitializationLine.unit_target)
            .filter(StockInitializationLine.shop_id == shop_id)
            .all()
        )
        initialized_set = {(pid, ut) for pid, ut in initialized_forms}

        # Forms already received via validated stock receipts
        validated_receipt_forms = (
            self._db.query(StockReceiptLine.product_id, StockReceiptLine.unit_target)
            .join(StockReceipt, StockReceiptLine.stock_receipt_id == StockReceipt.id)
            .filter(StockReceipt.shop_id == shop_id, StockReceipt.status == StockReceiptStatus.VALIDATED)
            .all()
        )
        receipt_set = {(pid, ut) for pid, ut in validated_receipt_forms}

        products = (
            self._db.query(Product)
            .join(Category, Product.category_id == Category.id)
            .filter(Product.shop_id == shop_id)
            .order_by(Product.name)
            .all()
        )

        items = []
        for product in products:
            forms_to_check = []
            if product.is_transformable:
                forms_to_check = [("principale", product.unit), ("secondaire", product.unit_secondaire)]
            else:
                forms_to_check = [("principale", product.unit)]
            # Check each form
            has_pending = False
            for unit_target, unit_label in forms_to_check:
                if (product.id, unit_target) in initialized_set:
                    continue
                if (product.id, unit_target) in receipt_set:
                    continue
                # also ensure form is valid for product
                if unit_target == "secondaire" and not product.is_transformable:
                    continue
                if unit_target == "secondaire" and not product.unit_secondaire:
                    continue
                items.append(
                    {
                        "product_id": product.id,
                        "product_name": product.name,
                        "category_id": product.category_id,
                        "category_name": product.category.name if product.category else "",
                        "unit_target": unit_target,
                        "unit_label": unit_label or unit_target,
                    }
                )
                has_pending = True
        return items

    def create(self, shop_id: int, user_id: int, data: dict) -> StockInitialization:
        lines_payload = data.get("lines") or []
        note = data.get("note")

        # Filter valid quantities: ignore absent/None; zero is error
        valid_lines = []
        for line in lines_payload:
            qty = line.get("quantity")
            if qty is None:
                continue  # ignore absent
            # check if explicitly zero
            try:
                qty_f = float(qty)
            except Exception:
                raise StockInitializationValidationError("Quantité invalide")
            if qty_f == 0:
                raise StockInitializationValidationError("La valeur zéro doit produire une erreur de validation explicite")
            if qty_f <= 0:
                raise StockInitializationValidationError("Une quantité renseignée doit être strictement positive")
            valid_lines.append({**line, "quantity": qty_f})

        if not valid_lines:
            raise StockInitializationValidationError("Aucune quantité valide fournie")

        # Get products in order
        product_ids = sorted({int(l["product_id"]) for l in valid_lines})
        # Lock products
        products_map = {}
        for pid in product_ids:
            product = self._products.get_by_id_locked(shop_id, pid)
            if not product:
                raise StockInitializationValidationError("Produit introuvable")
            products_map[pid] = product

        # Build initialization
        initialization = StockInitialization(
            shop_id=shop_id,
            note=note,
            created_by_id=user_id,
        )
        self._repo.save_new(initialization)

        init_lines = []
        for line in valid_lines:
            product_id = int(line["product_id"])
            unit_target = line["unit_target"]
            quantity = float(line["quantity"])
            product = products_map[product_id]

            if unit_target not in ("principale", "secondaire"):
                raise StockInitializationValidationError("Forme invalide")
            if unit_target == "secondaire":
                if not product.is_transformable or not product.unit_secondaire:
                    raise StockInitializationValidationError("Forme secondaire incompatible avec ce produit")
            # Check already initialized or already received
            if self._repo.has_initialization_for_form(shop_id, product_id, unit_target):
                raise StockInitializationValidationError("Cette forme a déjà été initialisée")
            # Check validated receipts
            existing_receipt = (
                self._db.query(StockReceiptLine)
                .join(StockReceipt, StockReceiptLine.stock_receipt_id == StockReceipt.id)
                .filter(
                    StockReceipt.shop_id == shop_id,
                    StockReceipt.status == StockReceiptStatus.VALIDATED,
                    StockReceiptLine.product_id == product_id,
                    StockReceiptLine.unit_target == unit_target,
                )
                .first()
            )
            if existing_receipt:
                raise StockInitializationValidationError("Cette forme a déjà reçu un approvisionnement validé")

            # Create line
            init_line = StockInitializationLine(
                stock_initialization_id=initialization.id,
                shop_id=shop_id,
                product_id=product.id,
                product_name=product.name,
                unit_target=unit_target,
                quantity=quantity,
            )
            self._db.add(init_line)
            init_lines.append(init_line)

            # Increment stock
            if unit_target == "secondaire":
                product.quantity_secondaire = float(product.quantity_secondaire or 0) + quantity
            else:
                product.quantity = float(product.quantity or 0) + quantity

            # Create movement
            self._db.add(
                StockMovement(
                    shop_id=shop_id,
                    product_id=product.id,
                    product_name=product.name,
                    source_type="stock_initialization",
                    source_id=initialization.id,
                    unit_target=unit_target,
                    quantity_delta=quantity,
                    created_by_id=user_id,
                )
            )

        try:
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        self._db.refresh(initialization)
        return initialization
