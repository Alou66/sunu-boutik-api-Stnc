from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String, Boolean
from sqlalchemy.orm import relationship

from app.db.session import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        # Filet de sécurité applicatif doublé ici : un article transformable a
        # forcément une forme secondaire et un taux de conversion positif (la
        # forme principale réutilise `unit`, déjà non-null). Voir la validation
        # côté service dans products_service.py — cette contrainte est le
        # dernier rempart.
        CheckConstraint(
            "NOT is_transformable OR ("
            "unit_secondaire IS NOT NULL AND conversion_ratio > 0 AND unit_price_secondaire >= 0"
            ")",
            name="ck_products_transformable_fields",
        ),
        CheckConstraint("quantity_secondaire >= 0", name="ck_products_quantity_secondaire_non_negative"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    reference = Column(String(100), nullable=True)
    unit_price = Column(Float, nullable=False, default=0)
    quantity = Column(Float, nullable=False, default=0)
    unit = Column(String(20), default="unite")
    pack_size = Column(Float, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

    # ---- Transformation (ex: 1 carton -> 4 seaux) ----
    # `unit` ci-dessus sert de nom à la forme principale (ex: "carton") quand
    # is_transformable est vrai ; `quantity` ci-dessus est le stock dans cette
    # forme principale. Les colonnes suivantes couvrent la forme secondaire.
    is_transformable = Column(Boolean, nullable=False, default=False, server_default="false")
    unit_secondaire = Column(String(20), nullable=True)
    # 1 unité de forme principale (`unit`) = conversion_ratio unité(s) de forme
    # secondaire (`unit_secondaire`).
    conversion_ratio = Column(Float, nullable=True)
    unit_price_secondaire = Column(Float, nullable=True)
    quantity_secondaire = Column(Float, nullable=False, default=0, server_default="0")

    shop = relationship("Shop", back_populates="products")
    category = relationship("Category", back_populates="products")
