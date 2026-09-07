from sqlalchemy.orm import Session, joinedload

from app.modules.billing.billing_model import AMOUNT_EPSILON, Invoice, InvoiceStatus
from app.modules.customers.customers_model import Client


class InvoiceRepository:
    def __init__(self, db: Session):
        self._db = db

    def list_paginated(
        self,
        shop_id: int,
        page: int,
        page_size: int,
        search: str | None,
        status_filter: str | None,
        date: str | None,
    ):
        from datetime import datetime, timedelta

        query = self._db.query(Invoice).filter(Invoice.shop_id == shop_id)
        if search:
            # Le nom du client n'est stocké dans invoices.client_name que pour les
            # factures sans client enregistré (saisie libre) : quand la facture est
            # liée à un Client (client_id renseigné), ce champ est laissé vide (voir
            # InvoiceService.create/update), donc la recherche doit aussi taper
            # dans clients.name via une jointure pour retrouver ces factures-là.
            query = query.outerjoin(Client, Invoice.client_id == Client.id).filter(
                (Invoice.number.ilike(f"%{search}%"))
                | (Invoice.client_name.ilike(f"%{search}%"))
                | (Client.name.ilike(f"%{search}%"))
            )
        if status_filter:
            status_enum = InvoiceStatus(status_filter)
            # Reproduit exactement la logique de Invoice.status (propriété Python
            # non stockée en base) pour que le filtre reste toujours cohérent avec elle.
            if status_enum == InvoiceStatus.UNPAID:
                query = query.filter(Invoice.amount_paid <= AMOUNT_EPSILON)
            elif status_enum == InvoiceStatus.PAID:
                query = query.filter(Invoice.amount_paid >= Invoice.total - AMOUNT_EPSILON)
            else:
                query = query.filter(
                    Invoice.amount_paid > AMOUNT_EPSILON,
                    Invoice.amount_paid < Invoice.total - AMOUNT_EPSILON,
                )
        if date:
            day_start = datetime.strptime(date, "%Y-%m-%d")
            day_end = day_start + timedelta(days=1)
            query = query.filter(Invoice.created_at >= day_start, Invoice.created_at < day_end)

        total = query.count()
        items = (
            query.options(joinedload(Invoice.lines))
            .order_by(Invoice.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total

    def get_by_id(self, shop_id: int, invoice_id: int) -> Invoice | None:
        return (
            self._db.query(Invoice)
            .options(joinedload(Invoice.lines))
            .filter(Invoice.id == invoice_id, Invoice.shop_id == shop_id)
            .first()
        )

    def count_for_shop(self, shop_id: int) -> int:
        return self._db.query(Invoice).filter(Invoice.shop_id == shop_id).count()

    def list_for_period(self, shop_id: int, start, end):
        return (
            self._db.query(Invoice)
            .options(joinedload(Invoice.lines))
            .filter(Invoice.shop_id == shop_id, Invoice.created_at >= start, Invoice.created_at < end)
            .order_by(Invoice.created_at.asc())
            .all()
        )
