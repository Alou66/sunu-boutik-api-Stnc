from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.identity.identity_model import User
from app.modules.stock_initializations.stock_initializations_dto import (
    StockInitializationCreate,
    StockInitializationOut,
    StockInitializationPendingOut,
)
from app.modules.stock_initializations.stock_initializations_mapper import to_initialization_out
from app.modules.stock_initializations.stock_initializations_service import (
    StockInitializationService,
    StockInitializationValidationError,
)

router = APIRouter(prefix="/stock-initializations", tags=["stock-initializations"])


@router.get("/pending", response_model=StockInitializationPendingOut)
def list_pending(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = StockInitializationService(db).list_pending(current_user.shop_id)
    return StockInitializationPendingOut(items=items, total=len(items))


@router.post("", response_model=StockInitializationOut, status_code=201)
def create_initialization(
    payload: StockInitializationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        initialization = StockInitializationService(db).create(current_user.shop_id, current_user.id, payload.model_dump())
    except StockInitializationValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_initialization_out(initialization)
