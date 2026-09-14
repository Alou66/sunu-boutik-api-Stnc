from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


def _normalize(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


class EmployeeCreate(BaseModel):
    full_name: str
    phone: str
    email: EmailStr
    password: str

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, v: str) -> str:
        return _normalize(v) or ""

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        return _normalize(v) or ""


class EmployeeUpdate(BaseModel):
    # Le propriétaire ne gère plus que le compte de l'employé (mot de passe,
    # activation) : nom, téléphone et email lui appartiennent et se modifient
    # uniquement via PATCH /auth/me (voir IdentityService.update_profile).
    password: Optional[str] = None
    is_active: Optional[bool] = None


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    phone: Optional[str] = None
    role: str
    is_active: bool
    must_change_password: bool
    created_at: datetime


class UserLookupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str


class EmployeeListOut(BaseModel):
    items: list[EmployeeOut]
    total: int
    page: int
    page_size: int
    total_pages: int
