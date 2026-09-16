from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.identity.identity_model import User
from app.modules.products.products_mapper import to_product_out
from app.modules.products.products_service import ProductNotFoundError
from app.modules.transformations.transformations_dto import (
    TransformationExecuteRequest,
    TransformationLogListOut,
    TransformationResultOut,
)
from app.modules.transformations.transformations_mapper import to_log_out
from app.modules.transformations.transformations_service import (
    InsufficientStockError,
    ProductNotTransformableError,
    TransformationService,
)

router = APIRouter(prefix="/transformations", tags=["transformations"])


@router.post("/execute", response_model=TransformationResultOut, status_code=201)
def execute_transformation(
    payload: TransformationExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        log, product = TransformationService(db).execute(
            current_user.shop_id, current_user.id,
            payload.product_id, payload.direction, payload.quantity, payload.note,
            idempotency_key=payload.idempotency_key,
        )
    except ProductNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (ProductNotTransformableError, InsufficientStockError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return TransformationResultOut(log=to_log_out(log), product=to_product_out(product))


@router.get("/history", response_model=TransformationLogListOut)
def list_history(
    page: int = 1,
    page_size: int = 20,
    product_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = TransformationService(db).list_history(current_user.shop_id, page, page_size, product_id)
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    total_pages = max((total + page_size - 1) // page_size, 1)

    return TransformationLogListOut(
        items=[to_log_out(log) for log in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
