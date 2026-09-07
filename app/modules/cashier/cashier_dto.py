from datetime import datetime

from pydantic import BaseModel


class CaisseSummaryOut(BaseModel):
    date: str
    invoices_count: int
    total_invoiced: float
    total_collected: float
    remaining: float


class CaisseEntryOut(BaseModel):
    id: int
    invoice_id: int
    invoice_number: str
    client_name: str
    amount: float
    created_at: datetime


class CaisseJournalOut(BaseModel):
    items: list[CaisseEntryOut]
    total: int
    page: int
    page_size: int
    total_pages: int
