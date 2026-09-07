from app.modules.categories.categories_dto import CategoryOut
from app.modules.categories.categories_model import Category


def to_category_out(category: Category) -> CategoryOut:
    return CategoryOut.model_validate(category)
