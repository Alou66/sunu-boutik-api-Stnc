from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StockInitializationLineIn(BaseModel):
    product_id: int
    unit_target: str
    quantity: Optional[float] = None


class StockInitializationCreate(BaseModel):
    lines: list[StockInitializationLineIn] = Field(default_factory=list)
    note: Optional[str] = None


class StockInitializationLinePendingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_name: str
    category_id: int
    category_name: str
    unit_target: str
    unit_label: str


class StockInitializationPendingOut(BaseModel):
    items: list[StockInitializationLinePendingOut]
    total: int


class StockInitializationLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str
    unit_target: str
    quantity: float
    created_at: datetime


class StockInitializationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shop_id: int
    note: Optional[str] = None
    created_by_id: Optional[int] = None
    created_at: datetime
    lines: list[StockInitializationLineOut] = []
