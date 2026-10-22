from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.identity.identity_model import User
from app.modules.stock_adjustments.stock_adjustments_dto import StockAdjustmentCreate, StockAdjustmentOut
from app.modules.stock_adjustments.stock_adjustments_service import StockAdjustmentService, StockAdjustmentValidationError

router = APIRouter(prefix="/stock-adjustments", tags=["stock-adjustments"])


@router.post("", response_model=StockAdjustmentOut, status_code=201)
def create_adjustment(
    payload: StockAdjustmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        adjustment = StockAdjustmentService(db).create(current_user.shop_id, current_user.id, payload.model_dump())
    except StockAdjustmentValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return adjustment
