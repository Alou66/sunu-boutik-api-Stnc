import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.session import Base


class StockReceiptStatus(str, enum.Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    CANCELLED = "cancelled"


class StockReceipt(Base):
    __tablename__ = "stock_receipts"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True, index=True)
    reference = Column(String(100), nullable=True)
    status = Column(Enum(StockReceiptStatus), nullable=False, default=StockReceiptStatus.DRAFT)
    total_cost = Column(Float, nullable=False, default=0)
    note = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    validated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    validated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    shop = relationship("Shop", back_populates="stock_receipts")
    supplier = relationship("Supplier")
    created_by = relationship("User", foreign_keys=[created_by_id])
    validated_by = relationship("User", foreign_keys=[validated_by_id])
    lines = relationship("StockReceiptLine", back_populates="receipt", cascade="all, delete-orphan")


class StockReceiptLine(Base):
    __tablename__ = "stock_receipt_lines"
    __table_args__ = (
        CheckConstraint("unit_target IN ('principale', 'secondaire')", name="ck_stock_receipt_lines_unit_target"),
        CheckConstraint("quantity > 0", name="ck_stock_receipt_lines_quantity_positive"),
        CheckConstraint("unit_cost >= 0", name="ck_stock_receipt_lines_unit_cost_non_negative"),
    )

    id = Column(Integer, primary_key=True, index=True)
    stock_receipt_id = Column(Integer, ForeignKey("stock_receipts.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    # Dénormalisé (comme InvoiceLine.product_name / TransformationLog.product_name) :
    # l'historique reste lisible même si l'article est renommé ou supprimé par la suite.
    product_name = Column(String(200), nullable=False)
    unit_target = Column(String(20), nullable=False)
    quantity = Column(Float, nullable=False)
    unit_cost = Column(Float, nullable=False, default=0)

    receipt = relationship("StockReceipt", back_populates="lines")
    product = relationship("Product")


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        Index("ix_stock_movements_shop_id_created_at", "shop_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    product_name = Column(String(200), nullable=False)
    source_type = Column(String(20), nullable=False, default="receipt")
    source_id = Column(Integer, nullable=False)
    unit_target = Column(String(20), nullable=False)
    # Positif à la validation d'une réception, négatif si on annule une
    # réception déjà validée (voir StockReceiptService.cancel).
    quantity_delta = Column(Float, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    shop = relationship("Shop")
    product = relationship("Product")
    created_by = relationship("User")
