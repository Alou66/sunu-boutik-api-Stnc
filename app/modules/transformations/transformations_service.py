from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.products.products_model import Product
from app.modules.products.products_repository import ProductRepository
from app.modules.products.products_service import ProductNotFoundError
from app.modules.transformations.transformations_model import TransformationDirection, TransformationLog
from app.modules.transformations.transformations_repository import TransformationRepository


class ProductNotTransformableError(Exception):
    pass


class InsufficientStockError(Exception):
    pass


class TransformationService:
    def __init__(self, db: Session):
        self._db = db
        self._products = ProductRepository(db)
        self._logs = TransformationRepository(db)

    def execute(
        self,
        shop_id: int,
        user_id: int,
        product_id: int,
        direction: TransformationDirection,
        quantity: float,
        note: str | None,
        idempotency_key: str | None = None,
    ) -> tuple[TransformationLog, Product]:
        # FOR UPDATE : verrouille l'article le temps de déplacer le stock entre
        # ses deux compteurs, pour empêcher deux transformations concurrentes sur
        # le même article de se marcher dessus (même logique que le décrément de
        # stock dans invoices.py::_apply_lines). Deux resoumissions identiques
        # (double clic, retry réseau) portent sur le même article : elles se
        # sérialisent donc déjà sur ce verrou, ce qui rend la vérification
        # d'idempotence ci-dessous fiable même sans transaction dédiée.
        product = self._products.get_by_id_locked(shop_id, product_id)
        if not product:
            raise ProductNotFoundError("Article introuvable")
        if not product.is_transformable:
            raise ProductNotTransformableError("Cet article n'est pas transformable")

        if idempotency_key:
            existing = self._logs.find_by_idempotency_key(shop_id, idempotency_key)
            if existing:
                return existing, product

        if direction == TransformationDirection.TO_SECONDAIRE:
            if product.quantity < quantity:
                raise InsufficientStockError(f"Stock insuffisant en {product.unit} pour cette transformation")
            quantity_to = quantity * product.conversion_ratio
            product.quantity -= quantity
            product.quantity_secondaire += quantity_to
            unit_from, unit_to = product.unit, product.unit_secondaire
        else:
            if product.quantity_secondaire < quantity:
                raise InsufficientStockError(f"Stock insuffisant en {product.unit_secondaire} pour cette transformation")
            quantity_to = quantity / product.conversion_ratio
            product.quantity_secondaire -= quantity
            product.quantity += quantity_to
            unit_from, unit_to = product.unit_secondaire, product.unit

        log = TransformationLog(
            shop_id=shop_id,
            product_id=product.id,
            product_name=product.name,
            direction=direction,
            unit_from=unit_from,
            unit_to=unit_to,
            quantity_from=quantity,
            quantity_to=quantity_to,
            note=note,
            created_by_id=user_id,
            idempotency_key=idempotency_key,
        )
        self._db.add(log)
        try:
            self._db.flush()
        except IntegrityError:
            self._db.rollback()
            if idempotency_key:
                existing = self._logs.find_by_idempotency_key(shop_id, idempotency_key)
                if existing:
                    product = self._products.get_by_id(shop_id, product_id)
                    return existing, product
            raise
        self._db.commit()
        self._db.refresh(product)
        self._db.refresh(log)
        return log, product

    def list_history(self, shop_id: int, page: int, page_size: int, product_id: int | None):
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        return self._logs.list_paginated(shop_id, page, page_size, product_id)
