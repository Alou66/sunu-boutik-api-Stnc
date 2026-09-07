from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.cashier.cashier_dto import CaisseJournalOut, CaisseSummaryOut
from app.modules.cashier.cashier_mapper import to_caisse_entry_out
from app.modules.cashier.cashier_service import CashierService, InvalidDateError
from app.modules.identity.identity_model import User

router = APIRouter(prefix="/caisse", tags=["caisse"])


@router.get("/summary", response_model=CaisseSummaryOut)
def get_daily_summary(
    date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        summary = CashierService(db).get_daily_summary(current_user.shop_id, date)
    except InvalidDateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CaisseSummaryOut(**summary)


@router.get("/journal", response_model=CaisseJournalOut)
def get_daily_journal(
    date: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        payments, total, page, page_size, total_pages = CashierService(db).get_daily_journal(
            current_user.shop_id, date, page, page_size
        )
    except InvalidDateError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return CaisseJournalOut(
        items=[to_caisse_entry_out(p) for p in payments],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
