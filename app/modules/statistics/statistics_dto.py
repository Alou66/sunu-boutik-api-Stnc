from pydantic import BaseModel


class StockOverviewOut(BaseModel):
    total_products: int
    invested_capital: float
    potential_sale_value: float
    latent_margin: float
    out_of_stock_count: int
    low_stock_count: int


class SalesPeriodOut(BaseModel):
    invoiced_total: float
    collected_total: float
    pending_total: float
    real_profit: float
    margin_rate: float
    invoices_count: int


class PurchasesPeriodOut(BaseModel):
    total_spent: float
    receipts_count: int


class DormantProductOut(BaseModel):
    product_id: int
    product_name: str
    quantity: float
    last_sale_at: str | None


class RankingsOut(BaseModel):
    dormant_products: list[DormantProductOut]


class StatisticsOut(BaseModel):
    date_from: str
    date_to: str
    stock: StockOverviewOut
    sales: SalesPeriodOut
    purchases: PurchasesPeriodOut
    rankings: RankingsOut
