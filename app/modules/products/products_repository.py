from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.modules.categories.categories_model import Category
from app.modules.products.products_model import Product


class ProductRepository:
    def __init__(self, db: Session):
        self._db = db

    def list_paginated(self, shop_id: int, page: int, page_size: int, search: str | None, transformable_only: bool):
        query = (
            self._db.query(Product)
            .join(Category, Product.category_id == Category.id)
            .options(joinedload(Product.category))
            .filter(Product.shop_id == shop_id)
        )
        if search:
            query = query.filter((Product.name.ilike(f"%{search}%")) | (Category.name.ilike(f"%{search}%")))
        if transformable_only:
            query = query.filter(Product.is_transformable.is_(True))
        total = query.count()
        items = query.order_by(Product.name).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def get_by_id(self, shop_id: int, product_id: int) -> Product | None:
        return (
            self._db.query(Product)
            .options(joinedload(Product.category))
            .filter(Product.id == product_id, Product.shop_id == shop_id)
            .first()
        )

    def get_by_id_locked(self, shop_id: int, product_id: int) -> Product | None:
        return (
            self._db.query(Product)
            .filter(Product.id == product_id, Product.shop_id == shop_id)
            .with_for_update()
            .first()
        )

    def exists_with_name(self, shop_id: int, name: str, exclude_id: int | None = None) -> bool:
        # Insensible à la casse, comme l'index uq_products_shop_id_upper_name.
        query = self._db.query(Product).filter(Product.shop_id == shop_id, func.upper(Product.name) == func.upper(name))
        if exclude_id is not None:
            query = query.filter(Product.id != exclude_id)
        return query.first() is not None

    def exists_in_category(self, category_id: int) -> bool:
        return self._db.query(Product).filter(Product.category_id == category_id).first() is not None

    def stats_aggregates(self, shop_id: int):
        base_query = self._db.query(Product).filter(Product.shop_id == shop_id)
        total_products = base_query.count()
        out_of_stock_count = base_query.filter(Product.quantity <= 0).count()

        total_stock_quantity, total_stock_value, average_price = (
            self._db.query(
                func.coalesce(func.sum(Product.quantity), 0),
                func.coalesce(func.sum(Product.unit_price * Product.quantity), 0),
                func.coalesce(func.avg(Product.unit_price), 0),
            )
            .filter(Product.shop_id == shop_id)
            .one()
        )
        return total_products, out_of_stock_count, total_stock_quantity, total_stock_value, average_price

    def save_new(self, product: Product) -> Product:
        self._db.add(product)
        self._db.commit()
        self._db.refresh(product)
        return product

    def save(self, product: Product) -> Product:
        self._db.commit()
        self._db.refresh(product)
        return product

    def delete(self, product: Product) -> None:
        self._db.delete(product)
        self._db.commit()
