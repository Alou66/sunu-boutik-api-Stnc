from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import relationship

from app.db.session import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        CheckConstraint(
            "amount_received IS NULL OR amount_received >= amount",
            name="ck_payments_received_gte_amount",
        ),
        Index("ix_payments_shop_id_created_at", "shop_id", "created_at"),
        # Index unique partiel (ignore les NULL) : deux soumissions portant la
        # même clé d'idempotence pour une même boutique ne peuvent pas créer
        # deux paiements, y compris en cas de course entre deux requêtes.
        Index(
            "uq_payments_shop_id_idempotency_key",
            "shop_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    # Montant crédité à la facture.
    amount = Column(Float, nullable=False)
    # Espèces effectivement remises par le client, si différent de `amount`
    # (permet de calculer le rendu monnaie sans le compter comme encaissé).
    amount_received = Column(Float, nullable=True)
    note = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Annulation "douce" : on garde la ligne pour l'historique de caisse plutôt
    # que de la supprimer physiquement.
    voided_at = Column(DateTime, nullable=True)
    voided_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Nullable en base (paiements jamais annulés) mais rendu obligatoire par le
    # schéma Pydantic de l'endpoint /void : sert la traçabilité même en
    # environnement mono-utilisateur.
    void_reason = Column(Text, nullable=True)
    # Idempotence : identifiant unique fourni par le client pour un essai
    # d'encaissement donné (voir PaymentCreate.idempotency_key). Permet de
    # rejouer une soumission sans créer de doublon, voir PaymentService.create.
    idempotency_key = Column(String(64), nullable=True)

    shop = relationship("Shop", back_populates="payments")
    invoice = relationship("Invoice", back_populates="payments")
    created_by = relationship("User", foreign_keys=[created_by_id])
    voided_by = relationship("User", foreign_keys=[voided_by_id])

    @property
    def change(self) -> float | None:
        if self.amount_received is None:
            return None
        return self.amount_received - self.amount

    @property
    def is_voided(self) -> bool:
        return self.voided_at is not None
