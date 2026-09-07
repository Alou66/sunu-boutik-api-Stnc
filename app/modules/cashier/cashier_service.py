from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.modules.billing.billing_model import Invoice
from app.modules.payments.payments_model import Payment


class InvalidDateError(Exception):
    pass


def parse_day(date: str | None) -> datetime:
    if not date:
        return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        return datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise InvalidDateError("Date invalide, format attendu AAAA-MM-JJ")


class CashierService:
    def __init__(self, db: Session):
        self._db = db

    def get_daily_summary(self, shop_id: int, date: str | None) -> dict:
        day_start = parse_day(date)
        day_end = day_start + timedelta(days=1)

        invoices_count, total_invoiced = (
            self._db.query(
                func.count(Invoice.id),
                func.coalesce(func.sum(Invoice.total), 0),
            )
            .filter(
                Invoice.shop_id == shop_id,
                Invoice.created_at >= day_start,
                Invoice.created_at < day_end,
            )
            .one()
        )

        # Le total encaissé compte les paiements réellement reçus ce jour-là
        # (Payment.created_at), pas Invoice.amount_paid des factures émises ce
        # jour-là : sinon un paiement tardif sur une vieille facture modifierait
        # rétroactivement le résumé d'une journée déjà clôturée, et ce total
        # divergerait de celui du journal (get_daily_journal) qui filtre déjà
        # ainsi. Les paiements annulés (voided_at renseigné) ne sont jamais des
        # encaissements.
        total_collected = (
            self._db.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(
                Payment.shop_id == shop_id,
                Payment.created_at >= day_start,
                Payment.created_at < day_end,
                Payment.voided_at.is_(None),
            )
            .scalar()
        )

        total_invoiced = float(total_invoiced)
        total_collected = float(total_collected)

        return {
            "date": day_start.strftime("%Y-%m-%d"),
            "invoices_count": invoices_count,
            "total_invoiced": total_invoiced,
            "total_collected": total_collected,
            "remaining": max(total_invoiced - total_collected, 0.0),
        }

    def get_daily_journal(self, shop_id: int, date: str | None, page: int, page_size: int):
        day_start = parse_day(date)
        day_end = day_start + timedelta(days=1)
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)

        # Un encaissement compte le jour où il a été reçu (Payment.created_at),
        # pas le jour d'émission de la facture : c'est un journal de caisse
        # (mouvements d'argent réels), pas un suivi de facturation.
        query = self._db.query(Payment).filter(
            Payment.shop_id == shop_id,
            Payment.created_at >= day_start,
            Payment.created_at < day_end,
            Payment.voided_at.is_(None),
        )

        total = query.count()
        payments = (
            query.options(joinedload(Payment.invoice).joinedload(Invoice.client))
            .order_by(Payment.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        total_pages = max((total + page_size - 1) // page_size, 1)

        return payments, total, page, page_size, total_pages
