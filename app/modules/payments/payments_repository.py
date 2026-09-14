from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.modules.payments.payments_model import Payment


class PaymentRepository:
    def __init__(self, db: Session):
        self._db = db

    def find_by_idempotency_key(self, shop_id: int, idempotency_key: str) -> Payment | None:
        return (
            self._db.query(Payment)
            .filter(Payment.shop_id == shop_id, Payment.idempotency_key == idempotency_key)
            .first()
        )

    def sum_active_for_invoice(self, invoice_id: int) -> float:
        total = (
            self._db.query(func.coalesce(func.sum(Payment.amount), 0.0))
            .filter(Payment.invoice_id == invoice_id, Payment.voided_at.is_(None))
            .scalar()
        )
        return float(total)

    def list_for_invoice(self, invoice_id: int) -> list[Payment]:
        return (
            self._db.query(Payment)
            .options(joinedload(Payment.created_by))
            .filter(Payment.invoice_id == invoice_id)
            .order_by(Payment.created_at)
            .all()
        )

    def get_by_id_for_invoice(self, invoice_id: int, payment_id: int) -> Payment | None:
        return (
            self._db.query(Payment)
            .filter(Payment.id == payment_id, Payment.invoice_id == invoice_id)
            .first()
        )
