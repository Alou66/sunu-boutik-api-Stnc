from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import relationship

from app.db.session import Base


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        # Index unique insensible à la casse : "Sucre", "sucre" et "SUCRE" sont la
        # même catégorie dans une boutique donnée. La vérification applicative
        # (CategoryRepository.exists_with_name) reste la première ligne de
        # défense ; cet index est le filet de sécurité en base.
        Index("uq_categories_shop_id_lower_name", "shop_id", text("lower(name)"), unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="categories")
    products = relationship("Product", back_populates="category")
