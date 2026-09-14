from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_owner
from app.db.session import get_db
from app.modules.identity.identity_model import User
from app.modules.statistics.statistics_dto import StatisticsOut
from app.modules.statistics.statistics_service import StatisticsService, StatisticsValidationError

router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get("", response_model=StatisticsOut)
def get_statistics(
    date_from: str,
    date_to: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_owner),
):
    try:
        data = StatisticsService(db).get_statistics(current_user.shop_id, date_from, date_to)
    except StatisticsValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StatisticsOut(**data)
