from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.identity.identity_model import User
from app.modules.stock_receipts.stock_receipts_dto import (
    StockMovementListOut,
    StockReceiptCreate,
    StockReceiptListOut,
    StockReceiptOut,
    StockReceiptUpdate,
)
from app.modules.stock_receipts.stock_receipts_mapper import to_movement_out, to_receipt_out
from app.modules.stock_receipts.stock_receipts_service import (
    InsufficientStockError,
    StockReceiptLineProductNotFoundError,
    StockReceiptLockedError,
    StockReceiptNotFoundError,
    StockReceiptService,
    StockReceiptValidationError,
    SupplierNotFoundError,
)

router = APIRouter(prefix="/stock-receipts", tags=["stock-receipts"])


@router.get("", response_model=StockReceiptListOut)
def list_stock_receipts(
    page: int = 1,
    page_size: int = 10,
    status: str | None = None,
    supplier_id: int | None = None,
    date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        items, total = StockReceiptService(db).list(current_user.shop_id, page, page_size, status, supplier_id, date)
    except StockReceiptValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    total_pages = max((total + page_size - 1) // page_size, 1)
    return StockReceiptListOut(
        items=[to_receipt_out(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/movements", response_model=StockMovementListOut)
def list_stock_movements(
    page: int = 1,
    page_size: int = 10,
    product_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    items, total = StockReceiptService(db).list_movements(current_user.shop_id, page, page_size, product_id)
    total_pages = max((total + page_size - 1) // page_size, 1)
    return StockMovementListOut(
        items=[to_movement_out(m) for m in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=StockReceiptOut, status_code=201)
def create_stock_receipt(payload: StockReceiptCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        receipt = StockReceiptService(db).create(current_user.shop_id, current_user.id, payload.model_dump())
    except SupplierNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except StockReceiptLineProductNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except StockReceiptValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_receipt_out(receipt)


@router.get("/{receipt_id}", response_model=StockReceiptOut)
def get_stock_receipt(receipt_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        receipt = StockReceiptService(db).get(current_user.shop_id, receipt_id)
    except StockReceiptNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return to_receipt_out(receipt)


@router.patch("/{receipt_id}", response_model=StockReceiptOut)
def update_stock_receipt(receipt_id: int, payload: StockReceiptUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        receipt = StockReceiptService(db).update(current_user.shop_id, receipt_id, payload.model_dump())
    except StockReceiptNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SupplierNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except StockReceiptLineProductNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (StockReceiptValidationError, StockReceiptLockedError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_receipt_out(receipt)


@router.delete("/{receipt_id}", status_code=204)
def delete_stock_receipt(receipt_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        StockReceiptService(db).delete(current_user.shop_id, receipt_id)
    except StockReceiptNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except StockReceiptLockedError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{receipt_id}/validate", response_model=StockReceiptOut)
def validate_stock_receipt(receipt_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        receipt = StockReceiptService(db).validate(current_user.shop_id, receipt_id, current_user.id)
    except StockReceiptNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except StockReceiptLineProductNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except StockReceiptLockedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_receipt_out(receipt)


@router.post("/{receipt_id}/cancel", response_model=StockReceiptOut)
def cancel_stock_receipt(receipt_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        receipt = StockReceiptService(db).cancel(current_user.shop_id, receipt_id, current_user.id)
    except StockReceiptNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except StockReceiptLineProductNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except StockReceiptLockedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_receipt_out(receipt)
