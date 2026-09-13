from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


def _normalize_name(name: Optional[str]) -> Optional[str]:
    if name is None:
        return None
    return name.strip()


class SupplierCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None
    note: Optional[str] = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return _normalize_name(v) or ""


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    note: Optional[str] = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_name(v)


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime


class SupplierListOut(BaseModel):
    items: list[SupplierOut]
    total: int
    page: int
    page_size: int
    total_pages: int
