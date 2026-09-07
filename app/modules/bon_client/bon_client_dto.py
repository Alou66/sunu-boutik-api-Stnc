from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


def _normalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.strip()


class BonClientCreate(BaseModel):
    title: str
    content: str

    @field_validator("title")
    @classmethod
    def normalize_title(cls, v: str) -> str:
        return _normalize_text(v) or ""

    @field_validator("content")
    @classmethod
    def normalize_content(cls, v: str) -> str:
        return _normalize_text(v) or ""


class BonClientUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_text(v)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_text(v)


class BonClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    created_at: datetime
    updated_at: datetime


class BonClientListOut(BaseModel):
    items: list[BonClientOut]
    total: int
    page: int
    page_size: int
    total_pages: int
