from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_name(name: Optional[str]) -> Optional[str]:
    if name is None:
        return None
    return name.strip().upper()


class ProductCreate(BaseModel):
    name: str
    category_id: int
    reference: Optional[str] = None
    unit_price: float = Field(ge=0)
    quantity: float = Field(default=0, ge=0)
    unit: str = "unite"
    pack_size: float = Field(default=1, ge=1)
    is_transformable: bool = False
    # Pertinents uniquement si is_transformable=True : `unit` ci-dessus sert
    # alors de nom à la forme principale (ex: "carton"). Validation croisée
    # faite dans le service, pas ici.
    unit_secondaire: Optional[str] = None
    conversion_ratio: Optional[float] = Field(default=None, gt=0)
    unit_price_secondaire: Optional[float] = Field(default=None, ge=0)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return _normalize_name(v) or ""


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category_id: Optional[int] = None
    reference: Optional[str] = None
    unit_price: Optional[float] = Field(default=None, ge=0)
    quantity: Optional[float] = Field(default=None, ge=0)
    unit: Optional[str] = None
    pack_size: Optional[float] = Field(default=None, ge=1)
    is_transformable: Optional[bool] = None
    unit_secondaire: Optional[str] = None
    conversion_ratio: Optional[float] = Field(default=None, gt=0)
    unit_price_secondaire: Optional[float] = Field(default=None, ge=0)
    quantity_secondaire: Optional[float] = Field(default=None, ge=0)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_name(v)


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category_id: int
    category_name: str
    reference: Optional[str] = None
    unit_price: float
    quantity: float
    unit: str
    pack_size: float
    is_transformable: bool
    unit_secondaire: Optional[str] = None
    conversion_ratio: Optional[float] = None
    unit_price_secondaire: Optional[float] = None
    quantity_secondaire: float
    created_at: datetime


class ProductListOut(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProductStatsOut(BaseModel):
    total_products: int
    total_stock_quantity: float
    total_stock_value: float
    out_of_stock_count: int
    average_price: float
