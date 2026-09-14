from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_owner, get_current_user
from app.db.session import get_db
from app.modules.employees.employees_dto import (
    EmployeeCreate,
    EmployeeListOut,
    EmployeeOut,
    EmployeeUpdate,
    UserLookupOut,
)
from app.modules.employees.employees_mapper import to_employee_out
from app.modules.employees.employees_service import (
    EmailAlreadyUsedError,
    EmployeeInUseError,
    EmployeeNotFoundError,
    EmployeeService,
    EmployeeValidationError,
)
from app.modules.identity.identity_model import User

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=EmployeeListOut)
def list_employees(
    page: int = 1,
    page_size: int = 10,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_owner: User = Depends(get_current_owner),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    items, total = EmployeeService(db).list(current_owner.shop_id, page, page_size, search)
    total_pages = max((total + page_size - 1) // page_size, 1)

    return EmployeeListOut(
        items=[to_employee_out(e) for e in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=EmployeeOut, status_code=201)
def create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
    current_owner: User = Depends(get_current_owner),
):
    try:
        employee = EmployeeService(db).create(current_owner.shop_id, payload.model_dump())
    except EmployeeValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except EmailAlreadyUsedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_employee_out(employee)


@router.get("/lookup", response_model=list[UserLookupOut])
def lookup_employees(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Accessible à tout utilisateur connecté (pas seulement le propriétaire) :
    # sert à peupler le filtre "par employé" des factures, que n'importe quel
    # employé doit pouvoir utiliser.
    users = EmployeeService(db).list_all_for_shop(current_user.shop_id)
    return [UserLookupOut.model_validate(u) for u in users]


@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_owner: User = Depends(get_current_owner),
):
    try:
        employee = EmployeeService(db).get(current_owner.shop_id, employee_id)
    except EmployeeNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return to_employee_out(employee)


@router.patch("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_owner: User = Depends(get_current_owner),
):
    data = payload.model_dump(exclude_unset=True)
    try:
        employee = EmployeeService(db).update(current_owner.shop_id, employee_id, data)
    except EmployeeNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except EmployeeValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except EmailAlreadyUsedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return to_employee_out(employee)


@router.delete("/{employee_id}", status_code=204)
def delete_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_owner: User = Depends(get_current_owner),
):
    try:
        EmployeeService(db).delete(current_owner.shop_id, employee_id)
    except EmployeeNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except EmployeeInUseError as e:
        raise HTTPException(status_code=400, detail=str(e))
