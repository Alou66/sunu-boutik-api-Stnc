from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.billing.billing_model import AMOUNT_EPSILON, Invoice
from app.modules.billing.billing_service import InvoiceNotFoundError
from app.modules.payments.payments_model import Payment
from app.modules.payments.payments_repository import PaymentRepository


class PaymentNotFoundError(Exception):
    pass


class InvoiceAlreadyPaidError(Exception):
    pass


class AmountExceedsBalanceError(Exception):
    pass


class PaymentAlreadyVoidedError(Exception):
    pass


class PaymentService:
    def __init__(self, db: Session):
        self._db = db
        self._repo = PaymentRepository(db)

    def _get_owned_invoice(self, shop_id: int, invoice_id: int) -> Invoice:
        invoice = self._db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.shop_id == shop_id).first()
        if not invoice:
            raise InvoiceNotFoundError("Facture introuvable")
        return invoice

    def _get_owned_invoice_locked(self, shop_id: int, invoice_id: int) -> Invoice:
        """Comme `_get_owned_invoice`, mais pose un verrou SELECT ... FOR UPDATE.

        Deux paiements simultanés sur la même facture se sérialisent ainsi sur
        cette ligne : le second attend que la transaction du premier se termine
        (commit ou rollback) avant de lire `amount_paid`, ce qui élimine le
        "lost update" (une des deux écritures qui écrase l'autre).
        """
        invoice = (
            self._db.query(Invoice)
            .filter(Invoice.id == invoice_id, Invoice.shop_id == shop_id)
            .with_for_update()
            .first()
        )
        if not invoice:
            raise InvoiceNotFoundError("Facture introuvable")
        return invoice

    def _recompute_amount_paid(self, invoice: Invoice) -> None:
        """Recalcule `amount_paid` à partir de la somme des paiements non annulés.

        `payments` reste la seule source de vérité : plutôt que d'incrémenter/
        décrémenter `amount_paid` en Python (ce qui peut diverger en cas de race
        condition ou de bug applicatif), on le recalcule intégralement à chaque
        changement, pendant que la ligne invoice est verrouillée (FOR UPDATE).
        """
        invoice.amount_paid = self._repo.sum_active_for_invoice(invoice.id)

    def list_for_invoice(self, shop_id: int, invoice_id: int) -> list[Payment]:
        invoice = self._get_owned_invoice(shop_id, invoice_id)
        return self._repo.list_for_invoice(invoice.id)

    def create(
        self,
        shop_id: int,
        user_id: int,
        invoice_id: int,
        amount: float,
        amount_received: float | None,
        note: str | None,
        idempotency_key: str | None,
    ) -> Payment:
        # Verrou FOR UPDATE : bloque les autres transactions qui tenteraient de
        # payer/annuler un paiement sur la même facture tant que celle-ci n'est
        # pas commitée/rollback, pour éviter tout dépassement concurrent du solde.
        invoice = self._get_owned_invoice_locked(shop_id, invoice_id)

        # Idempotence : si cette tentative d'encaissement a déjà abouti (retry
        # réseau, double soumission), on renvoie le paiement existant plutôt que
        # d'en créer un second. Le verrou ci-dessus sérialise déjà les requêtes
        # concurrentes sur cette même facture, donc cette vérification suffit dans
        # l'immense majorité des cas ; l'index unique partiel en base
        # (uq_payments_shop_id_idempotency_key) reste le filet de sécurité si deux
        # requêtes portant la même clé visaient deux factures différentes.
        if idempotency_key:
            existing = self._repo.find_by_idempotency_key(shop_id, idempotency_key)
            if existing:
                return existing

        balance_due = invoice.balance_due
        if balance_due <= AMOUNT_EPSILON:
            raise InvoiceAlreadyPaidError("Cette facture est déjà payée")
        if amount > balance_due + AMOUNT_EPSILON:
            raise AmountExceedsBalanceError(f"Le montant dépasse le solde restant ({balance_due:,.0f} FCFA)")

        payment = Payment(
            shop_id=shop_id,
            invoice_id=invoice.id,
            amount=amount,
            amount_received=amount_received,
            note=note,
            created_by_id=user_id,
            idempotency_key=idempotency_key,
        )
        self._db.add(payment)
        try:
            self._db.flush()
        except IntegrityError:
            self._db.rollback()
            if idempotency_key:
                existing = self._repo.find_by_idempotency_key(shop_id, idempotency_key)
                if existing:
                    return existing
            raise
        self._recompute_amount_paid(invoice)

        self._db.commit()
        self._db.refresh(payment)
        return payment

    def void(self, shop_id: int, user_id: int, invoice_id: int, payment_id: int, reason: str) -> Payment:
        invoice = self._get_owned_invoice_locked(shop_id, invoice_id)
        payment = self._repo.get_by_id_for_invoice(invoice.id, payment_id)
        if not payment:
            raise PaymentNotFoundError("Paiement introuvable")

        if payment.is_voided:
            raise PaymentAlreadyVoidedError("Ce paiement est déjà annulé")

        payment.voided_at = datetime.utcnow()
        payment.voided_by_id = user_id
        payment.void_reason = reason
        self._db.flush()
        self._recompute_amount_paid(invoice)

        self._db.commit()
        self._db.refresh(payment)
        return payment
