from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.billing.billing_model import InvoiceStatus


class InvoiceLineCreate(BaseModel):
    product_id: int
    quantity: float
    unit_price: Optional[float] = Field(default=None, ge=0)
    # Forme vendue pour un article transformable ("principale" ou
    # "secondaire") ; ignoré pour un article non transformable.
    form: Optional[Literal["principale", "secondaire"]] = None


class InvoiceCreate(BaseModel):
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    note: Optional[str] = None
    lines: list[InvoiceLineCreate]


class InvoiceUpdate(BaseModel):
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    note: Optional[str] = None
    lines: list[InvoiceLineCreate]


class InvoiceCancelRequest(BaseModel):
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Le motif d'annulation est requis")
        return v


class InvoiceLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str
    quantity: float
    unit_price: float
    line_total: float
    form: Optional[str] = None


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    total: float
    amount_paid: float
    balance_due: float
    status: InvoiceStatus
    note: Optional[str] = None
    created_by_id: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    cancelled_at: Optional[datetime] = None
    cancelled_by_id: Optional[int] = None
    cancelled_by_name: Optional[str] = None
    cancel_reason: Optional[str] = None
    lines: list[InvoiceLineOut] = []


class InvoiceListOut(BaseModel):
    items: list[InvoiceOut]
    total: int
    page: int
    page_size: int
    total_pages: int
