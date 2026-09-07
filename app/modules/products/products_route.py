from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.modules.identity.identity_model import User
from app.db.session import get_db
from app.modules.categories.categories_service import CategoryNotFoundError
from app.modules.products.products_dto import ProductCreate, ProductListOut, ProductOut, ProductStatsOut, ProductUpdate
from app.modules.products.products_mapper import to_product_out
from app.modules.products.products_service import (
    DuplicateProductNameError,
    ProductInUseError,
    ProductNotFoundError,
    ProductService,
    ProductValidationError,
)

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ProductListOut)
def list_products(
    page: int = 1,
    page_size: int = 10,
    search: str | None = None,
    transformable_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    items, total = ProductService(db).list(current_user.shop_id, page, page_size, search, transformable_only)
    total_pages = max((total + page_size - 1) // page_size, 1)

    return ProductListOut(
        items=[to_product_out(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/stats", response_model=ProductStatsOut)
def product_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return ProductStatsOut(**ProductService(db).stats(current_user.shop_id))


@router.post("", response_model=ProductOut, status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        product = ProductService(db).create(current_user.shop_id, payload.model_dump())
    except CategoryNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DuplicateProductNameError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ProductValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_product_out(product)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        product = ProductService(db).get(current_user.shop_id, product_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return to_product_out(product)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    data = payload.model_dump(exclude_unset=True)
    try:
        product = ProductService(db).update(current_user.shop_id, product_id, data)
    except (ProductNotFoundError, CategoryNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DuplicateProductNameError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ProductValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_product_out(product)


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        ProductService(db).delete(current_user.shop_id, product_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ProductInUseError as e:
        raise HTTPException(status_code=400, detail=str(e))
