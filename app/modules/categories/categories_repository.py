from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.categories.categories_model import Category


class CategoryRepository:
    def __init__(self, db: Session):
        self._db = db

    def list_paginated(self, shop_id: int, page: int, page_size: int, search: str | None) -> tuple[list[Category], int]:
        query = self._db.query(Category).filter(Category.shop_id == shop_id)
        if search:
            query = query.filter(Category.name.ilike(f"%{search}%"))
        total = query.count()
        items = query.order_by(Category.name).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def get_by_id(self, shop_id: int, category_id: int) -> Category | None:
        return self._db.query(Category).filter(Category.id == category_id, Category.shop_id == shop_id).first()

    def exists_with_name(self, shop_id: int, name: str, exclude_id: int | None = None) -> bool:
        query = self._db.query(Category).filter(
            Category.shop_id == shop_id,
            func.lower(Category.name) == name.strip().lower(),
        )
        if exclude_id is not None:
            query = query.filter(Category.id != exclude_id)
        return query.first() is not None

    def save_new(self, category: Category) -> Category:
        self._db.add(category)
        self._db.commit()
        self._db.refresh(category)
        return category

    def save(self, category: Category) -> Category:
        self._db.commit()
        self._db.refresh(category)
        return category

    def delete(self, category: Category) -> None:
        self._db.delete(category)
        self._db.commit()
