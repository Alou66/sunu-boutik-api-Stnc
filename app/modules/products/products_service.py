from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.categories.categories_repository import CategoryRepository
from app.modules.categories.categories_service import CategoryNotFoundError
from app.modules.products.products_model import Product
from app.modules.products.products_repository import ProductRepository


class ProductNotFoundError(Exception):
    pass


class DuplicateProductNameError(Exception):
    pass


class ProductValidationError(Exception):
    pass


class ProductInUseError(Exception):
    pass


_UNIQUE_NAME_INDEX = "uq_products_shop_id_upper_name"


def _is_duplicate_name_violation(exc: IntegrityError) -> bool:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == _UNIQUE_NAME_INDEX


def validate_transformation_fields(
    is_transformable: bool,
    unit: str | None,
    unit_secondaire: str | None,
    conversion_ratio: float | None,
    unit_price_secondaire: float | None,
) -> tuple[str, str | None, float | None, float | None]:
    """Vérifie la cohérence des champs de transformation et normalise les libellés.

    Miroir de la CheckConstraint ck_products_transformable_fields côté base,
    qui reste le dernier filet de sécurité.
    """
    if not is_transformable:
        return (unit or "unite"), None, None, None

    principale = (unit or "").strip()
    secondaire = (unit_secondaire or "").strip()
    if not principale:
        raise ProductValidationError("La forme principale est requise pour un article transformable")
    if not secondaire:
        raise ProductValidationError("La forme secondaire est requise pour un article transformable")
    if principale.lower() == secondaire.lower():
        raise ProductValidationError("La forme principale et la forme secondaire doivent être différentes")
    if conversion_ratio is None or conversion_ratio <= 0:
        raise ProductValidationError("Le taux de conversion doit être un nombre positif")
    if unit_price_secondaire is None or unit_price_secondaire < 0:
        raise ProductValidationError("Le prix unitaire de la forme secondaire est requis")
    return principale, secondaire, conversion_ratio, unit_price_secondaire


_TRANSFORMATION_FIELDS = {"is_transformable", "unit", "unit_secondaire", "conversion_ratio", "unit_price_secondaire"}


class ProductService:
    def __init__(self, db: Session):
        self._db = db
        self._repo = ProductRepository(db)
        self._categories = CategoryRepository(db)

    def list(self, shop_id: int, page: int, page_size: int, search: str | None, transformable_only: bool):
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        return self._repo.list_paginated(shop_id, page, page_size, search, transformable_only)

    def stats(self, shop_id: int) -> dict:
        total_products, out_of_stock_count, total_stock_quantity, total_stock_value, average_price = (
            self._repo.stats_aggregates(shop_id)
        )
        return {
            "total_products": total_products,
            "total_stock_quantity": float(total_stock_quantity or 0),
            "total_stock_value": float(total_stock_value or 0),
            "out_of_stock_count": out_of_stock_count,
            "average_price": float(average_price or 0),
        }

    def get(self, shop_id: int, product_id: int) -> Product:
        product = self._repo.get_by_id(shop_id, product_id)
        if not product:
            raise ProductNotFoundError("Article introuvable")
        return product

    def get_locked(self, shop_id: int, product_id: int) -> Product:
        product = self._repo.get_by_id_locked(shop_id, product_id)
        if not product:
            raise ProductNotFoundError("Article introuvable")
        return product

    def create(self, shop_id: int, data: dict) -> Product:
        if not data["name"]:
            raise ProductValidationError("Le nom de l'article est requis")
        if self._categories.get_by_id(shop_id, data["category_id"]) is None:
            raise CategoryNotFoundError("Catégorie introuvable")
        if self._repo.exists_with_name(shop_id, data["name"]):
            raise DuplicateProductNameError("Un article portant ce nom existe déjà dans cette boutique.")

        unit, unit_secondaire, conversion_ratio, unit_price_secondaire = validate_transformation_fields(
            data["is_transformable"], data["unit"], data["unit_secondaire"],
            data["conversion_ratio"], data["unit_price_secondaire"],
        )
        data = {
            **data,
            "unit": unit,
            "unit_secondaire": unit_secondaire,
            "conversion_ratio": conversion_ratio,
            "unit_price_secondaire": unit_price_secondaire,
        }
        product = Product(shop_id=shop_id, **data)
        try:
            return self._repo.save_new(product)
        except IntegrityError as exc:
            # Deux créations simultanées du même nom passent toutes deux le
            # contrôle exists_with_name ci-dessus : l'index unique tranche.
            self._db.rollback()
            if _is_duplicate_name_violation(exc):
                raise DuplicateProductNameError("Un article portant ce nom existe déjà dans cette boutique.")
            raise

    def update(self, shop_id: int, product_id: int, data: dict) -> Product:
        # `data` ne contient que les champs explicitement fournis par
        # l'appelant (le routeur ne passe que payload.model_dump(exclude_unset=True)).
        product = self.get(shop_id, product_id)

        if "name" in data:
            if not data["name"]:
                raise ProductValidationError("Le nom de l'article est requis")
            if self._repo.exists_with_name(shop_id, data["name"], exclude_id=product.id):
                raise DuplicateProductNameError("Un article portant ce nom existe déjà dans cette boutique.")
        if "category_id" in data:
            if self._categories.get_by_id(shop_id, data["category_id"]) is None:
                raise CategoryNotFoundError("Catégorie introuvable")

        if _TRANSFORMATION_FIELDS & data.keys():
            is_transformable = data.get("is_transformable", product.is_transformable)
            effective_quantity_secondaire = data.get("quantity_secondaire", product.quantity_secondaire)
            if not is_transformable and effective_quantity_secondaire > 0:
                raise ProductValidationError(
                    f"Impossible de désactiver la transformation : il reste {effective_quantity_secondaire:g} "
                    f"unité(s) en forme secondaire ({product.unit_secondaire}). Transformez-les d'abord."
                )
            unit, unit_secondaire, conversion_ratio, unit_price_secondaire = validate_transformation_fields(
                is_transformable,
                data.get("unit", product.unit),
                data.get("unit_secondaire", product.unit_secondaire),
                data.get("conversion_ratio", product.conversion_ratio),
                data.get("unit_price_secondaire", product.unit_price_secondaire),
            )
            data.update(
                is_transformable=is_transformable,
                unit=unit,
                unit_secondaire=unit_secondaire,
                conversion_ratio=conversion_ratio,
                unit_price_secondaire=unit_price_secondaire,
            )

        for field, value in data.items():
            setattr(product, field, value)
        try:
            return self._repo.save(product)
        except IntegrityError as exc:
            self._db.rollback()
            if _is_duplicate_name_violation(exc):
                raise DuplicateProductNameError("Un article portant ce nom existe déjà dans cette boutique.")
            raise

    def delete(self, shop_id: int, product_id: int) -> None:
        # InvoiceLine (module invoices, pas encore migré), TransformationLog et
        # les lignes/mouvements d'approvisionnement ne sont pas des tables de
        # products : vérifiées ici directement plutôt que via ProductRepository,
        # qui ne connaît que Product. Toute table portant une clé étrangère vers
        # products.id doit figurer ici, sinon la suppression échoue en violation
        # de clé étrangère (500) au lieu d'une erreur métier (400).
        from app.modules.billing.billing_model import InvoiceLine
        from app.modules.stock_receipts.stock_receipts_model import StockMovement, StockReceiptLine
        from app.modules.transformations.transformations_model import TransformationLog

        product = self.get(shop_id, product_id)
        if self._db.query(InvoiceLine).filter(InvoiceLine.product_id == product_id).first():
            raise ProductInUseError("Impossible de supprimer : cet article est déjà utilisé dans une ou plusieurs factures")
        if self._db.query(TransformationLog).filter(TransformationLog.product_id == product_id).first():
            raise ProductInUseError("Impossible de supprimer : cet article a un historique de transformations")
        if self._db.query(StockReceiptLine).filter(StockReceiptLine.product_id == product_id).first():
            raise ProductInUseError("Impossible de supprimer : cet article est déjà utilisé dans une ou plusieurs réceptions de stock")
        if self._db.query(StockMovement).filter(StockMovement.product_id == product_id).first():
            raise ProductInUseError("Impossible de supprimer : cet article a un historique de mouvements de stock")
        self._repo.delete(product)
