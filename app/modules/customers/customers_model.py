from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import relationship

from app.db.session import Base


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("shop_id", "phone", name="uq_clients_shop_phone"),
        # Index unique insensible à la casse : "Jean Diop" et "jean diop" sont
        # considérés comme le même client dans une boutique donnée. Le vrai
        # filet de sécurité contre les doublons de nom, la vérification
        # applicative se trouve dans customers_service.py (_ensure_name_available).
        Index(
            "uq_clients_shop_id_lower_name",
            "shop_id",
            text("lower(name)"),
            unique=True,
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    phone = Column(String(50), nullable=True)
    address = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="clients")
