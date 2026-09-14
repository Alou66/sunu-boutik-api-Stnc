from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.modules.employees.employees_repository import EmployeeRepository
from app.modules.identity.identity_model import User, UserRole


class EmployeeNotFoundError(Exception):
    pass


class EmployeeValidationError(Exception):
    pass


class EmailAlreadyUsedError(Exception):
    pass


class EmployeeInUseError(Exception):
    pass


MIN_PASSWORD_LENGTH = 6


class EmployeeService:
    def __init__(self, db: Session):
        self._db = db
        self._repo = EmployeeRepository(db)

    def list(self, shop_id: int, page: int, page_size: int, search: str | None) -> tuple[list[User], int]:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        return self._repo.list_paginated(shop_id, page, page_size, search)

    def list_all_for_shop(self, shop_id: int) -> list[User]:
        return self._repo.list_all_for_shop(shop_id)

    def get(self, shop_id: int, employee_id: int) -> User:
        employee = self._repo.get_by_id(shop_id, employee_id)
        if not employee:
            raise EmployeeNotFoundError("Employé introuvable")
        return employee

    def create(self, shop_id: int, data: dict) -> User:
        if not data["full_name"]:
            raise EmployeeValidationError("Le nom complet est requis")
        if not data["phone"]:
            raise EmployeeValidationError("Le téléphone est requis")
        if len(data["password"]) < MIN_PASSWORD_LENGTH:
            raise EmployeeValidationError(f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères")
        if self._repo.find_by_email(data["email"]):
            raise EmailAlreadyUsedError("Cet email est déjà utilisé")

        employee = User(
            shop_id=shop_id,
            full_name=data["full_name"],
            email=data["email"],
            phone=data["phone"],
            hashed_password=hash_password(data["password"]),
            role=UserRole.EMPLOYEE,
            is_active=True,
            # Le mot de passe est choisi par le propriétaire, pas par l'employé :
            # on force son changement à la première connexion (même mécanisme
            # que pour le propriétaire après approbation de la boutique, voir
            # AdminService.approve_shop).
            must_change_password=True,
        )
        return self._repo.save_new(employee)

    def update(self, shop_id: int, employee_id: int, data: dict) -> User:
        # Le propriétaire ne gère ici que le compte de l'employé (mot de passe,
        # activation) : nom, téléphone et email appartiennent à l'employé et ne
        # se modifient que via PATCH /auth/me (IdentityService.update_profile).
        employee = self.get(shop_id, employee_id)

        if "password" in data and data["password"]:
            if len(data["password"]) < MIN_PASSWORD_LENGTH:
                raise EmployeeValidationError(f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères")
            employee.hashed_password = hash_password(data["password"])
            # Ce nouveau mot de passe a été choisi par le propriétaire (ex. après
            # oubli) : l'employé doit en choisir un à lui à sa prochaine connexion.
            employee.must_change_password = True

        if "is_active" in data and data["is_active"] is not None and data["is_active"] != employee.is_active:
            employee.is_active = data["is_active"]
            if not employee.is_active:
                # Coupe immédiatement toute session déjà ouverte : les JWT émis
                # avant ce changement portent l'ancien token_version et seront
                # rejetés par get_current_user dès la prochaine requête.
                employee.token_version += 1

        return self._repo.save(employee)

    def delete(self, shop_id: int, employee_id: int) -> None:
        employee = self.get(shop_id, employee_id)
        if self._repo.has_related_records(employee.id):
            raise EmployeeInUseError(
                "Impossible de supprimer : cet employé a des opérations associées. Désactivez-le plutôt."
            )
        self._repo.delete(employee)
