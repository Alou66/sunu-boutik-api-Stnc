from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.identity.identity_model import User
from app.modules.customers.customers_dto import ClientCreate, ClientListOut, ClientOut, ClientUpdate
from app.modules.customers.customers_mapper import to_client_out
from app.modules.customers.customers_service import (
    ClientConflictError,
    ClientInUseError,
    ClientNotFoundError,
    ClientPhoneConflictError,
    ClientService,
    ClientValidationError,
    DuplicateClientNameError,
    DuplicateClientPhoneError,
)

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("", response_model=ClientListOut)
def list_clients(
    page: int = 1,
    page_size: int = 10,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    items, total = ClientService(db).list(current_user.shop_id, page, page_size, search)
    total_pages = max((total + page_size - 1) // page_size, 1)

    return ClientListOut(
        items=[to_client_out(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=ClientOut, status_code=201)
def create_client(payload: ClientCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        client = ClientService(db).create(current_user.shop_id, payload.model_dump())
    except (DuplicateClientPhoneError, DuplicateClientNameError) as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (ClientPhoneConflictError, ClientConflictError, ClientValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_client_out(client)


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        client = ClientService(db).get(current_user.shop_id, client_id)
    except ClientNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return to_client_out(client)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(client_id: int, payload: ClientUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    data = payload.model_dump(exclude_unset=True)
    try:
        client = ClientService(db).update(current_user.shop_id, client_id, data)
    except ClientNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DuplicateClientNameError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (ClientPhoneConflictError, ClientConflictError, ClientValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_client_out(client)


@router.delete("/{client_id}", status_code=204)
def delete_client(client_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        ClientService(db).delete(current_user.shop_id, client_id)
    except ClientNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ClientInUseError as e:
        raise HTTPException(status_code=409, detail=str(e))
