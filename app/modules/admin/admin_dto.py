from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ShopAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    status: str
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    owner_email: Optional[str] = None
    owner_name: Optional[str] = None


class ShopStatsOut(BaseModel):
    shop_id: int
    shop_name: str
    status: str
    products_count: int
    clients_count: int
    invoices_count: int
    total_revenue: float
    users_count: int


class RejectRequest(BaseModel):
    reason: Optional[str] = None


class OverviewOut(BaseModel):
    total_shops: int
    pending_shops: int
    approved_shops: int
    rejected_shops: int
    total_invoices: int
    total_revenue: float


class ShopListOut(BaseModel):
    items: list[ShopAdminOut]
    total: int
    page: int
    page_size: int
    total_pages: int
