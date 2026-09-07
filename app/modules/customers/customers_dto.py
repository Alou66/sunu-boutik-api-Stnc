from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


def _validate_phone(phone: Optional[str]) -> Optional[str]:
    if phone is None:
        return None
    phone = phone.strip()
    if not phone:
        return None
    if not phone.isdigit() or len(phone) != 9:
        raise ValueError("Le téléphone doit contenir exactement 9 chiffres")
    return phone


class ClientCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        return _validate_phone(v)


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        return _validate_phone(v)


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None
    created_at: datetime


class ClientListOut(BaseModel):
    items: list[ClientOut]
    total: int
    page: int
    page_size: int
    total_pages: int
