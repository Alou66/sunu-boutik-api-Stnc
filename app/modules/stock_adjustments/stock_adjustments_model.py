from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.session import Base


class StockAdjustment(Base):
    __tablename__ = "stock_adjustments"
    __table_args__ = (
        CheckConstraint("adjustment_type IN ('entry', 'exit')", name="ck_stock_adjustments_type"),
        Index("ix_stock_adjustments_shop_id_created_at", "shop_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    product_name = Column(String(200), nullable=False)
    unit_target = Column(String(20), nullable=False)
    adjustment_type = Column(String(10), nullable=False)
    quantity = Column(Float, nullable=False)
    quantity_delta = Column(Float, nullable=False)
    stock_before = Column(Float, nullable=False)
    stock_after = Column(Float, nullable=False)
    reason = Column(Text, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    shop = relationship("Shop")
    product = relationship("Product")
    created_by = relationship("User")
