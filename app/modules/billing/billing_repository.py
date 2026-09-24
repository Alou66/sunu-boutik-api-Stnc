from sqlalchemy import Integer, cast, func
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
        employee_id: int | None = None,
    ):
        from datetime import datetime, timedelta

        query = self._db.query(Invoice).filter(Invoice.shop_id == shop_id)
        if employee_id is not None:
            query = query.filter(Invoice.created_by_id == employee_id)
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
            if status_enum == InvoiceStatus.CANCELLED:
                query = query.filter(Invoice.cancelled_at.isnot(None))
            elif status_enum == InvoiceStatus.UNPAID:
                query = query.filter(Invoice.cancelled_at.is_(None), Invoice.amount_paid <= AMOUNT_EPSILON)
            elif status_enum == InvoiceStatus.PAID:
                query = query.filter(
                    Invoice.cancelled_at.is_(None), Invoice.amount_paid >= Invoice.total - AMOUNT_EPSILON
                )
            else:
                query = query.filter(
                    Invoice.cancelled_at.is_(None),
                    Invoice.amount_paid > AMOUNT_EPSILON,
                    Invoice.amount_paid < Invoice.total - AMOUNT_EPSILON,
                )
        if date:
            day_start = datetime.strptime(date, "%Y-%m-%d")
            day_end = day_start + timedelta(days=1)
            query = query.filter(Invoice.created_at >= day_start, Invoice.created_at < day_end)

        total = query.count()
        items = (
            query.options(joinedload(Invoice.lines), joinedload(Invoice.created_by))
            .order_by(Invoice.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total

    def get_by_id(self, shop_id: int, invoice_id: int) -> Invoice | None:
        return (
            self._db.query(Invoice)
            .options(joinedload(Invoice.lines), joinedload(Invoice.created_by), joinedload(Invoice.cancelled_by))
            .filter(Invoice.id == invoice_id, Invoice.shop_id == shop_id)
            .first()
        )

    def get_by_id_locked(self, shop_id: int, invoice_id: int) -> Invoice | None:
        """Comme `get_by_id`, mais pose un verrou SELECT ... FOR UPDATE.

        Utilisé par cancel/delete : sérialise toute tentative concurrente de
        paiement, annulation ou suppression sur la même facture (même schéma
        que PaymentService._get_owned_invoice_locked). Sans jointure sur les
        lignes : Postgres refuse FOR UPDATE du côté "nullable" d'un outer join
        (joinedload sur une relation to-many) ; `invoice.lines` reste
        accessible en lazy-load normal après ce verrou.
        """
        return (
            self._db.query(Invoice)
            .filter(Invoice.id == invoice_id, Invoice.shop_id == shop_id)
            .with_for_update()
            .first()
        )

    def find_by_idempotency_key(self, shop_id: int, idempotency_key: str) -> Invoice | None:
        return (
            self._db.query(Invoice)
            .options(joinedload(Invoice.lines), joinedload(Invoice.created_by))
            .filter(Invoice.shop_id == shop_id, Invoice.idempotency_key == idempotency_key)
            .first()
        )

    def next_sequence_for_shop(self, shop_id: int) -> int:
        """Prochain suffixe numérique de numéro de facture pour cette boutique.

        Basé sur le MAX du suffixe déjà utilisé parmi les factures existantes
        (extrait de "FA{date}-{suffixe}"), plutôt que sur un COUNT(*) : un
        COUNT(*) redescend quand une facture annulée est supprimée
        (InvoiceService.delete) et régénérerait alors un numéro déjà pris par
        une facture plus récente encore existante, provoquant un conflit de
        numérotation systématique. Le MAX ne redescend que si la facture
        supprimée était celle au suffixe le plus élevé, auquel cas réutiliser
        ce numéro est sans risque puisque plus aucune facture ne le porte.
        """
        max_suffix = (
            self._db.query(func.max(cast(func.split_part(Invoice.number, "-", 2), Integer)))
            .filter(Invoice.shop_id == shop_id)
            .scalar()
        )
        return (max_suffix or 0) + 1
