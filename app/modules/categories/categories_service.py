from sqlalchemy.orm import Session

from app.modules.categories.categories_model import Category
from app.modules.categories.categories_repository import CategoryRepository


class CategoryNotFoundError(Exception):
    pass


class DuplicateCategoryNameError(Exception):
    pass


class CategoryValidationError(Exception):
    pass


class CategoryHasProductsError(Exception):
    pass


class CategoryService:
    def __init__(self, db: Session):
        self._db = db
        self._repo = CategoryRepository(db)

    def list(self, shop_id: int, page: int, page_size: int, search: str | None) -> tuple[list[Category], int]:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        return self._repo.list_paginated(shop_id, page, page_size, search)

    def get(self, shop_id: int, category_id: int) -> Category:
        category = self._repo.get_by_id(shop_id, category_id)
        if not category:
            raise CategoryNotFoundError("Catégorie introuvable")
        return category

    def create(self, shop_id: int, name: str) -> Category:
        name = name.strip()
        if not name:
            raise CategoryValidationError("Le nom de la catégorie est requis")
        if self._repo.exists_with_name(shop_id, name):
            raise DuplicateCategoryNameError("Une catégorie avec ce nom existe déjà")
        category = Category(shop_id=shop_id, name=name)
        return self._repo.save_new(category)

    def update(self, shop_id: int, category_id: int, name: str | None) -> Category:
        # name=None signifie "champ non fourni, ne pas toucher" — le routeur ne
        # passe `name` que si la clé était présente dans le payload
        # (payload.model_dump(exclude_unset=True)).
        category = self.get(shop_id, category_id)
        if name is not None:
            name = name.strip()
            if not name:
                raise CategoryValidationError("Le nom de la catégorie est requis")
            if self._repo.exists_with_name(shop_id, name, exclude_id=category_id):
                raise DuplicateCategoryNameError("Une catégorie avec ce nom existe déjà")
            category.name = name
        return self._repo.save(category)

    def delete(self, shop_id: int, category_id: int) -> None:
        from app.modules.products.products_repository import ProductRepository

        category = self.get(shop_id, category_id)
        if ProductRepository(self._db).exists_in_category(category_id):
            raise CategoryHasProductsError("Impossible de supprimer : des articles sont rattachés à cette catégorie")
        self._repo.delete(category)
