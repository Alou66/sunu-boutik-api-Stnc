from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.session import Base


class StockInitialization(Base):
    __tablename__ = "stock_initializations"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    note = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    shop = relationship("Shop")
    created_by = relationship("User")
    lines = relationship("StockInitializationLine", back_populates="initialization", cascade="all, delete-orphan")


class StockInitializationLine(Base):
    __tablename__ = "stock_initialization_lines"
    __table_args__ = (
        CheckConstraint("unit_target IN ('principale', 'secondaire')", name="ck_stock_initialization_lines_unit_target"),
        CheckConstraint("quantity > 0", name="ck_stock_initialization_lines_quantity_positive"),
        UniqueConstraint("shop_id", "product_id", "unit_target", name="uq_stock_initialization_lines_shop_product_unit_target"),
        Index("ix_stock_initialization_lines_shop_id_product_id", "shop_id", "product_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    stock_initialization_id = Column(Integer, ForeignKey("stock_initializations.id"), nullable=False, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    product_name = Column(String(200), nullable=False)
    unit_target = Column(String(20), nullable=False)
    quantity = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    initialization = relationship("StockInitialization", back_populates="lines")
    product = relationship("Product")
    shop = relationship("Shop")
