import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Float, Index, Integer, String, Text, text
from sqlalchemy.orm import relationship

from app.db.session import Base


class TransformationDirection(str, enum.Enum):
    TO_SECONDAIRE = "to_secondaire"
    TO_PRINCIPALE = "to_principale"


class TransformationLog(Base):
    __tablename__ = "transformation_logs"
    __table_args__ = (
        Index("ix_transformation_logs_shop_id_created_at", "shop_id", "created_at"),
        # Filet de sécurité contre la double soumission (double clic sur
        # "Transformer", retry réseau) : même mécanisme que
        # uq_payments_shop_id_idempotency_key, voir TransformationService.execute.
        Index(
            "uq_transformation_logs_shop_id_idempotency_key",
            "shop_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    # Dénormalisé (comme InvoiceLine.product_name) : l'historique reste lisible
    # même si l'article est renommé ou supprimé par la suite.
    product_name = Column(String(200), nullable=False)
    direction = Column(Enum(TransformationDirection), nullable=False)
    unit_from = Column(String(20), nullable=False)
    unit_to = Column(String(20), nullable=False)
    quantity_from = Column(Float, nullable=False)
    quantity_to = Column(Float, nullable=False)
    note = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Idempotence : identifiant unique fourni par le client pour une tentative
    # de transformation donnée (même mécanisme que Payment.idempotency_key).
    # Permet de rejouer une soumission (double clic, retry réseau) sans
    # déplacer le stock une seconde fois pour la même opération.
    idempotency_key = Column(String(64), nullable=True)

    shop = relationship("Shop", back_populates="transformation_logs")
    product = relationship("Product")
    created_by = relationship("User")
