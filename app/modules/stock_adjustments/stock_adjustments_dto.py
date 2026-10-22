from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class StockAdjustmentCreate(BaseModel):
    product_id: int
    unit_target: str
    adjustment_type: str  # entry or exit
    quantity: float
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("Le motif est obligatoire")
        return str(v).strip()


class StockAdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shop_id: int
    product_id: int
    product_name: str
    unit_target: str
    adjustment_type: str
    quantity: float
    quantity_delta: float
    stock_before: float
    stock_after: float
    reason: str
    created_by_id: Optional[int] = None
    created_at: datetime
