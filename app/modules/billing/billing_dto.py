from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

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
    created_at: datetime
    lines: list[InvoiceLineOut] = []


class InvoiceListOut(BaseModel):
    items: list[InvoiceOut]
    total: int
    page: int
    page_size: int
    total_pages: int
