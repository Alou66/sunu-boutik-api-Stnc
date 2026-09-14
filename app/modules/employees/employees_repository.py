from sqlalchemy.orm import Session

from app.modules.identity.identity_model import User, UserRole


class EmployeeRepository:
    def __init__(self, db: Session):
        self._db = db

    def list_paginated(self, shop_id: int, page: int, page_size: int, search: str | None) -> tuple[list[User], int]:
        query = self._db.query(User).filter(User.shop_id == shop_id, User.role == UserRole.EMPLOYEE)
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(User.full_name.ilike(pattern))
        total = query.count()
        items = query.order_by(User.full_name).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def list_all_for_shop(self, shop_id: int) -> list[User]:
        # Tous les utilisateurs de la boutique (propriétaire, admin, employés) :
        # sert le filtre "par employé" des factures, où l'auteur peut être
        # n'importe lequel d'entre eux (voir Invoice.created_by_id).
        return self._db.query(User).filter(User.shop_id == shop_id).order_by(User.full_name).all()

    def get_by_id(self, shop_id: int, employee_id: int) -> User | None:
        return (
            self._db.query(User)
            .filter(User.id == employee_id, User.shop_id == shop_id, User.role == UserRole.EMPLOYEE)
            .first()
        )

    def find_by_email(self, email: str) -> User | None:
        return self._db.query(User).filter(User.email == email).first()

    def save_new(self, employee: User) -> User:
        self._db.add(employee)
        self._db.commit()
        self._db.refresh(employee)
        return employee

    def save(self, employee: User) -> User:
        self._db.commit()
        self._db.refresh(employee)
        return employee

    def delete(self, employee: User) -> None:
        self._db.delete(employee)
        self._db.commit()

    def has_related_records(self, employee_id: int) -> bool:
        from app.modules.payments.payments_model import Payment
        from app.modules.stock_receipts.stock_receipts_model import StockMovement, StockReceipt
        from app.modules.transformations.transformations_model import TransformationLog

        checks = [
            self._db.query(StockReceipt.id)
            .filter((StockReceipt.created_by_id == employee_id) | (StockReceipt.validated_by_id == employee_id)),
            self._db.query(StockMovement.id).filter(StockMovement.created_by_id == employee_id),
            self._db.query(TransformationLog.id).filter(TransformationLog.created_by_id == employee_id),
            self._db.query(Payment.id).filter((Payment.created_by_id == employee_id) | (Payment.voided_by_id == employee_id)),
        ]
        return any(query.first() is not None for query in checks)
