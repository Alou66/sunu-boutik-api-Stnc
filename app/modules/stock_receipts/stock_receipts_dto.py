from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.modules.stock_receipts.stock_receipts_model import StockReceiptStatus


class StockReceiptLineIn(BaseModel):
    product_id: int
    unit_target: Literal["principale", "secondaire"] = "principale"
    quantity: float = Field(gt=0)
    unit_cost: Optional[float] = Field(default=None, ge=0)


class StockReceiptCreate(BaseModel):
    supplier_id: Optional[int] = None
    reference: Optional[str] = None
    note: Optional[str] = None
    lines: list[StockReceiptLineIn]


class StockReceiptUpdate(BaseModel):
    supplier_id: Optional[int] = None
    reference: Optional[str] = None
    note: Optional[str] = None
    lines: list[StockReceiptLineIn]


class StockReceiptLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str
    unit_target: str
    quantity: float
    unit_cost: float


class StockReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    reference: Optional[str] = None
    status: StockReceiptStatus
    total_cost: float
    note: Optional[str] = None
    created_by_id: Optional[int] = None
    created_by_name: Optional[str] = None
    validated_by_id: Optional[int] = None
    validated_by_name: Optional[str] = None
    validated_at: Optional[datetime] = None
    created_at: datetime
    lines: list[StockReceiptLineOut] = []


class StockReceiptListOut(BaseModel):
    items: list[StockReceiptOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class StockMovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str
    source_type: str
    source_id: int
    unit_target: str
    quantity_delta: float
    created_by_id: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime


class StockMovementListOut(BaseModel):
    items: list[StockMovementOut]
    total: int
    page: int
    page_size: int
    total_pages: int
