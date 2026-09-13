from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.identity.identity_model import User
from app.modules.suppliers.suppliers_dto import SupplierCreate, SupplierListOut, SupplierOut, SupplierUpdate
from app.modules.suppliers.suppliers_mapper import to_supplier_out
from app.modules.suppliers.suppliers_service import (
    SupplierInUseError,
    SupplierNotFoundError,
    SupplierService,
    SupplierValidationError,
)

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("", response_model=SupplierListOut)
def list_suppliers(
    page: int = 1,
    page_size: int = 10,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    items, total = SupplierService(db).list(current_user.shop_id, page, page_size, search)
    total_pages = max((total + page_size - 1) // page_size, 1)

    return SupplierListOut(
        items=[to_supplier_out(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=SupplierOut, status_code=201)
def create_supplier(payload: SupplierCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        supplier = SupplierService(db).create(current_user.shop_id, payload.model_dump())
    except SupplierValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_supplier_out(supplier)


@router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        supplier = SupplierService(db).get(current_user.shop_id, supplier_id)
    except SupplierNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return to_supplier_out(supplier)


@router.patch("/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: int, payload: SupplierUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    data = payload.model_dump(exclude_unset=True)
    try:
        supplier = SupplierService(db).update(current_user.shop_id, supplier_id, data)
    except SupplierNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SupplierValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_supplier_out(supplier)


@router.delete("/{supplier_id}", status_code=204)
def delete_supplier(supplier_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        SupplierService(db).delete(current_user.shop_id, supplier_id)
    except SupplierNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SupplierInUseError as e:
        raise HTTPException(status_code=400, detail=str(e))
