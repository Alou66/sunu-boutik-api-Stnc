import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import relationship

from app.db.session import Base

# Tolérance utilisée pour comparer des montants Float (évite qu'une erreur
# d'arrondi flottant laisse une facture indéfiniment "partielle").
AMOUNT_EPSILON = 0.01


class InvoiceStatus(str, enum.Enum):
    UNPAID = "unpaid"
    PARTIAL = "partial"
    PAID = "paid"
    CANCELLED = "cancelled"


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("amount_paid >= 0", name="ck_invoices_amount_paid_non_negative"),
        # Tolérance flottante alignée sur AMOUNT_EPSILON : empêche qu'une facture
        # se retrouve avec un montant payé supérieur au total, y compris en cas
        # de bug applicatif (dernier filet de sécurité, la vraie protection contre
        # les accès concurrents est le verrou FOR UPDATE posé dans payments.py).
        CheckConstraint("amount_paid <= total + 0.01", name="ck_invoices_amount_paid_lte_total"),
        # Les stats de caisse journalières filtrent toujours par (shop_id, created_at)
        # (voir app/routers/caisse.py et list_invoices) : un index composite sert ces
        # deux prédicats en un seul scan, plutôt que de combiner deux index simples.
        Index("ix_invoices_shop_id_created_at", "shop_id", "created_at"),
        # Filet de sécurité contre les doublons de numéro de facture : le vrai
        # verrou anti-race-condition est le FOR UPDATE posé sur la ligne shop
        # dans billing_service.py (lock_shop_for_numbering), cette contrainte
        # garantit qu'aucun doublon ne peut être committé même si ce verrou est
        # contourné.
        UniqueConstraint("shop_id", "number", name="uq_invoices_shop_id_number"),
        # Filet de sécurité contre la double soumission (double clic sur
        # "Valider", retry réseau) : même mécanisme que
        # uq_payments_shop_id_idempotency_key, voir InvoiceService.create.
        Index(
            "uq_invoices_shop_id_idempotency_key",
            "shop_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    client_name = Column(String(150), nullable=True)
    number = Column(String(50), nullable=False)
    total = Column(Float, nullable=False, default=0)
    # Dénormalisé et mis à jour transactionnellement à chaque paiement créé/annulé
    # (même logique que `total`, recalculé dans _apply_lines). Le statut de la
    # facture n'est jamais stocké : il est dérivé de amount_paid via la propriété
    # `status` ci-dessous, pour garantir qu'il ne peut pas diverger du montant payé.
    amount_paid = Column(Float, nullable=False, default=0, server_default="0")
    note = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Annulation "douce" (même logique que Payment.voided_at) : la facture et
    # ses lignes sont conservées pour l'historique, le stock déjà décrémenté
    # par InvoiceService.cancel est recrédité, et le statut dérivé ci-dessous
    # bascule sur CANCELLED indépendamment de amount_paid. Une facture
    # annulée peut ensuite être supprimée définitivement (InvoiceService.delete).
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Nullable en base (factures jamais annulées) mais rendu obligatoire par le
    # schéma Pydantic de l'endpoint /cancel, pour la traçabilité.
    cancel_reason = Column(Text, nullable=True)
    # Idempotence : identifiant unique fourni par le client pour une tentative
    # de création de facture donnée (voir InvoiceCreate.idempotency_key et
    # PaymentCreate.idempotency_key pour le même mécanisme). Permet de rejouer
    # une soumission (double clic sur "Valider", retry réseau) sans créer deux
    # factures pour la même vente.
    idempotency_key = Column(String(64), nullable=True)

    shop = relationship("Shop", back_populates="invoices")
    client = relationship("Client")
    created_by = relationship("User", foreign_keys=[created_by_id])
    cancelled_by = relationship("User", foreign_keys=[cancelled_by_id])
    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan")
    payments = relationship(
        "Payment",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="Payment.created_at",
    )

    @property
    def balance_due(self) -> float:
        return max(self.total - self.amount_paid, 0.0)

    @property
    def is_cancelled(self) -> bool:
        return self.cancelled_at is not None

    @property
    def status(self) -> InvoiceStatus:
        if self.is_cancelled:
            return InvoiceStatus.CANCELLED
        if self.amount_paid <= AMOUNT_EPSILON:
            return InvoiceStatus.UNPAID
        if self.amount_paid >= self.total - AMOUNT_EPSILON:
            return InvoiceStatus.PAID
        return InvoiceStatus.PARTIAL


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (
        CheckConstraint("form IN ('principale', 'secondaire')", name="ck_invoice_lines_form"),
    )

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    product_name = Column(String(200), nullable=False)
    quantity = Column(Float, nullable=False)
    unit_price = Column(Float, nullable=False)
    line_total = Column(Float, nullable=False)
    # Coût d'achat capturé au moment de la vente (products.purchase_price, ou
    # purchase_price_secondaire si form == "secondaire"), pour calculer un
    # bénéfice réel par ligne dans le module Statistiques. NULL pour les lignes
    # créées avant l'introduction de ce champ : le calcul des statistiques
    # applique alors un fallback sur le purchase_price ACTUEL du produit.
    cost_price = Column(Float, nullable=True)
    # Forme vendue pour un article transformable ("principale" ou
    # "secondaire") : détermine quel compteur de stock du Product a été
    # décrémenté, pour pouvoir le créditer correctement si la ligne est
    # supprimée/modifiée (voir _apply_lines dans billing_service.py). Nul pour
    # un article non transformable.
    form = Column(String(20), nullable=True)

    invoice = relationship("Invoice", back_populates="lines")
    product = relationship("Product")
