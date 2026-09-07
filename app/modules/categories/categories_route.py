from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.identity.identity_model import User
from app.modules.categories.categories_dto import CategoryCreate, CategoryListOut, CategoryOut, CategoryUpdate
from app.modules.categories.categories_mapper import to_category_out
from app.modules.categories.categories_service import (
    CategoryHasProductsError,
    CategoryNotFoundError,
    CategoryService,
    CategoryValidationError,
    DuplicateCategoryNameError,
)

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=CategoryListOut)
def list_categories(
    page: int = 1,
    page_size: int = 10,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    items, total = CategoryService(db).list(current_user.shop_id, page, page_size, search)
    total_pages = max((total + page_size - 1) // page_size, 1)

    return CategoryListOut(
        items=[to_category_out(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        category = CategoryService(db).create(current_user.shop_id, payload.name)
    except CategoryValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DuplicateCategoryNameError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_category_out(category)


@router.get("/{category_id}", response_model=CategoryOut)
def get_category(category_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        category = CategoryService(db).get(current_user.shop_id, category_id)
    except CategoryNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return to_category_out(category)


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, payload: CategoryUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    data = payload.model_dump(exclude_unset=True)
    try:
        category = CategoryService(db).update(current_user.shop_id, category_id, data.get("name"))
    except CategoryNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (CategoryValidationError, DuplicateCategoryNameError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_category_out(category)


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        CategoryService(db).delete(current_user.shop_id, category_id)
    except CategoryNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CategoryHasProductsError as e:
        raise HTTPException(status_code=400, detail=str(e))
