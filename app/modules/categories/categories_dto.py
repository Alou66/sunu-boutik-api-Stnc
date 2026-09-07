from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


def _normalize_name(name: Optional[str]) -> Optional[str]:
    if name is None:
        return None
    return name.strip().upper()


class CategoryCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return _normalize_name(v) or ""


class CategoryUpdate(BaseModel):
    name: Optional[str] = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_name(v)


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


class CategoryListOut(BaseModel):
    items: list[CategoryOut]
    total: int
    page: int
    page_size: int
    total_pages: int
