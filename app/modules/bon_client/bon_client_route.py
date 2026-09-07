from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.identity.identity_model import User
from app.modules.bon_client.bon_client_dto import BonClientCreate, BonClientListOut, BonClientOut, BonClientUpdate
from app.modules.bon_client.bon_client_mapper import to_bon_client_out
from app.modules.bon_client.bon_client_service import BonClientNotFoundError, BonClientService, BonClientValidationError

router = APIRouter(prefix="/bons-clients", tags=["bons-clients"])


@router.get("", response_model=BonClientListOut)
def list_bons_clients(
    page: int = 1,
    page_size: int = 10,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    items, total = BonClientService(db).list(current_user.shop_id, page, page_size, search)
    total_pages = max((total + page_size - 1) // page_size, 1)

    return BonClientListOut(
        items=[to_bon_client_out(n) for n in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=BonClientOut, status_code=201)
def create_bon_client(payload: BonClientCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        bon_client = BonClientService(db).create(current_user.shop_id, payload.title, payload.content)
    except BonClientValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_bon_client_out(bon_client)


@router.get("/{bon_client_id}", response_model=BonClientOut)
def get_bon_client(bon_client_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        bon_client = BonClientService(db).get(current_user.shop_id, bon_client_id)
    except BonClientNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return to_bon_client_out(bon_client)


@router.patch("/{bon_client_id}", response_model=BonClientOut)
def update_bon_client(bon_client_id: int, payload: BonClientUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    data = payload.model_dump(exclude_unset=True)
    try:
        bon_client = BonClientService(db).update(current_user.shop_id, bon_client_id, data.get("title"), data.get("content"))
    except BonClientNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except BonClientValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_bon_client_out(bon_client)


@router.delete("/{bon_client_id}", status_code=204)
def delete_bon_client(bon_client_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        BonClientService(db).delete(current_user.shop_id, bon_client_id)
    except BonClientNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
