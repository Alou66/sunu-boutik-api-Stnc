from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.billing.billing_model import AMOUNT_EPSILON, Invoice, InvoiceLine
from app.modules.billing.billing_repository import InvoiceRepository
from app.modules.customers.customers_model import Client
from app.modules.products.products_model import Product


class InvoiceNotFoundError(Exception):
    pass


class InvoiceValidationError(Exception):
    pass


class InvoiceClientNotFoundError(Exception):
    pass


class InvoiceLineProductNotFoundError(Exception):
    pass


class InsufficientStockError(Exception):
    pass


class NumberingConflictError(Exception):
    pass


class InvoiceLockedError(Exception):
    pass


class InvoiceAlreadyCancelledError(Exception):
    pass


class InvoiceNotCancelledError(Exception):
    pass


class InvoiceService:
    def __init__(self, db: Session):
        self._db = db
        self._repo = InvoiceRepository(db)

    # ---- Lecture ----

    def list(
        self,
        shop_id: int,
        page: int,
        page_size: int,
        search: str | None,
        date: str | None,
        status_filter: str | None,
        employee_id: int | None = None,
    ):
        from app.modules.billing.billing_model import InvoiceStatus

        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)

        if status_filter:
            try:
                InvoiceStatus(status_filter)
            except ValueError:
                raise InvoiceValidationError("Statut invalide")
        if date:
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise InvoiceValidationError("Date invalide, format attendu AAAA-MM-JJ")

        return self._repo.list_paginated(shop_id, page, page_size, search, status_filter, date, employee_id)

    def get(self, shop_id: int, invoice_id: int) -> Invoice:
        invoice = self._repo.get_by_id(shop_id, invoice_id)
        if not invoice:
            raise InvoiceNotFoundError("Facture introuvable")
        return invoice

    def list_for_period(self, shop_id: int, start, end):
        return self._repo.list_for_period(shop_id, start, end)

    def get_shop(self, shop_id: int):
        from app.modules.identity.identity_model import Shop

        return self._db.query(Shop).filter(Shop.id == shop_id).first()

    def get_client_unscoped(self, client_id: int | None):
        if client_id is None:
            return None
        return self._db.query(Client).filter(Client.id == client_id).first()

    # ---- Numérotation & verrouillage ----

    def _generate_invoice_number(self, shop_id: int) -> str:
        seq = self._repo.next_sequence_for_shop(shop_id)
        return f"FA{datetime.utcnow().strftime('%Y%m%d')}-{seq:04d}"

    def _lock_shop_for_numbering(self, shop_id: int) -> None:
        """Verrouille la ligne shop le temps de générer+insérer le numéro de facture.

        Deux créations de facture simultanées se sérialisent ainsi sur cette ligne :
        la seconde attend que la transaction de la première se termine (commit ou
        rollback) avant de recompter les factures existantes, ce qui élimine la race
        condition du COUNT()+1 (double clic, deux onglets, etc.). La contrainte
        UNIQUE(shop_id, number) en base reste le filet de sécurité ultime.
        """
        from app.modules.identity.identity_model import Shop

        self._db.query(Shop).filter(Shop.id == shop_id).with_for_update().first()

    # ---- Lignes ----

    def _apply_lines(self, invoice: Invoice, lines_payload: list, shop_id: int, revert_existing: bool = False) -> None:
        if revert_existing:
            for old_line in list(invoice.lines):
                # FOR UPDATE : verrouille la ligne produit le temps de créditer son
                # stock, pour rester cohérent avec le verrou posé lors du
                # décrément ci-dessous et éviter tout lost update concurrent.
                product = self._db.query(Product).filter(Product.id == old_line.product_id).with_for_update().first()
                if product:
                    if old_line.form == "secondaire":
                        product.quantity_secondaire += old_line.quantity
                    else:
                        product.quantity += old_line.quantity
                self._db.delete(old_line)
            self._db.flush()

        total = 0.0
        for line in lines_payload:
            # FOR UPDATE : bloque toute autre transaction qui tenterait de lire/
            # décrémenter ce même produit tant que celle-ci n'est pas commitée,
            # pour empêcher la survente en cas de factures concurrentes sur le
            # même article (double clic, deux onglets, etc.).
            product = (
                self._db.query(Product)
                .filter(Product.id == line.product_id, Product.shop_id == shop_id)
                .with_for_update()
                .first()
            )
            if not product:
                raise InvoiceLineProductNotFoundError(f"Article {line.product_id} introuvable")
            if line.quantity <= 0:
                raise InvoiceValidationError("La quantité doit être positive")

            product_name = product.name
            if product.is_transformable:
                form = line.form or "principale"
                if form == "secondaire":
                    available, default_price, label = product.quantity_secondaire, product.unit_price_secondaire, product.unit_secondaire
                    default_cost_price = product.purchase_price_secondaire
                else:
                    available, default_price, label = product.quantity, product.unit_price, product.unit
                    default_cost_price = product.purchase_price
                if available < line.quantity:
                    raise InsufficientStockError(f"Stock insuffisant pour {product.name} ({label})")
                if form == "secondaire":
                    product.quantity_secondaire -= line.quantity
                else:
                    product.quantity -= line.quantity
                # Distingue la forme vendue sur la facture imprimée (ex: "SEAU
                # Chocopain 5kg"), car un même article peut apparaître en
                # principale et en secondaire sur des lignes différentes.
                product_name = f"{label.upper()} {product.name}"
            else:
                form = None
                default_price = product.unit_price
                default_cost_price = product.purchase_price
                if product.quantity < line.quantity:
                    raise InsufficientStockError(f"Stock insuffisant pour {product.name}")
                product.quantity -= line.quantity

            unit_price = line.unit_price if line.unit_price is not None else default_price
            line_total = unit_price * line.quantity
            total += line_total

            self._db.add(InvoiceLine(
                invoice_id=invoice.id,
                product_id=product.id,
                product_name=product_name,
                quantity=line.quantity,
                unit_price=unit_price,
                line_total=line_total,
                form=form,
                cost_price=default_cost_price,
            ))

        invoice.total = total

    # ---- Écriture ----

    def create(
        self,
        shop_id: int,
        client_id: int | None,
        client_name: str | None,
        note: str | None,
        lines_payload: list,
        created_by_id: int | None = None,
    ) -> Invoice:
        if not lines_payload:
            raise InvoiceValidationError("La facture doit contenir au moins un article")

        if client_id is not None:
            client = self._db.query(Client).filter(Client.id == client_id, Client.shop_id == shop_id).first()
            if not client:
                raise InvoiceClientNotFoundError("Client introuvable")

        client_name = (client_name or "").strip() or None

        self._lock_shop_for_numbering(shop_id)

        invoice = Invoice(
            shop_id=shop_id,
            client_id=client_id,
            client_name=client_name if client_id is None else None,
            number=self._generate_invoice_number(shop_id),
            note=note,
            created_by_id=created_by_id,
            total=0,
        )
        self._db.add(invoice)
        try:
            self._db.flush()
        except IntegrityError:
            self._db.rollback()
            raise NumberingConflictError("Conflit lors de la génération du numéro de facture, veuillez réessayer")

        self._apply_lines(invoice, lines_payload, shop_id)

        self._db.commit()
        self._db.refresh(invoice)
        return invoice

    def update(self, shop_id: int, invoice_id: int, client_id: int | None, client_name: str | None, note: str | None, lines_payload: list) -> Invoice:
        invoice = self.get(shop_id, invoice_id)

        if invoice.is_cancelled:
            raise InvoiceLockedError("Cette facture est annulée, elle ne peut plus être modifiée")

        if invoice.amount_paid > AMOUNT_EPSILON:
            raise InvoiceLockedError(
                "Impossible de modifier une facture ayant déjà reçu un paiement. "
                "Annulez d'abord le ou les paiements associés."
            )

        if not lines_payload:
            raise InvoiceValidationError("La facture doit contenir au moins un article")

        if client_id is not None:
            client = self._db.query(Client).filter(Client.id == client_id, Client.shop_id == shop_id).first()
            if not client:
                raise InvoiceClientNotFoundError("Client introuvable")

        client_name = (client_name or "").strip() or None

        invoice.client_id = client_id
        invoice.client_name = client_name if client_id is None else None
        invoice.note = note

        self._apply_lines(invoice, lines_payload, shop_id, revert_existing=True)

        self._db.commit()
        self._db.refresh(invoice)
        return invoice

    # ---- Annulation / suppression ----

    def cancel(self, shop_id: int, invoice_id: int, user_id: int, reason: str) -> Invoice:
        # Verrou FOR UPDATE : sérialise avec un paiement ou une autre annulation
        # concurrente sur la même facture (même logique que PaymentService.void).
        invoice = self._repo.get_by_id_locked(shop_id, invoice_id)
        if not invoice:
            raise InvoiceNotFoundError("Facture introuvable")

        if invoice.is_cancelled:
            raise InvoiceAlreadyCancelledError("Cette facture est déjà annulée")

        if invoice.amount_paid > AMOUNT_EPSILON:
            raise InvoiceLockedError(
                "Impossible d'annuler une facture ayant déjà reçu un paiement. "
                "Annulez d'abord le ou les paiements associés."
            )

        # Recrédite le stock de chaque ligne. Verrouille les produits dans un
        # ordre déterministe (product_id croissant) pour éviter un deadlock si
        # une autre facture/réception verrouille les mêmes articles en parallèle
        # (même précaution que StockReceiptService.cancel).
        for line in sorted(invoice.lines, key=lambda l: l.product_id):
            product = self._db.query(Product).filter(Product.id == line.product_id).with_for_update().first()
            if product:
                if line.form == "secondaire":
                    product.quantity_secondaire += line.quantity
                else:
                    product.quantity += line.quantity

        invoice.cancelled_at = datetime.utcnow()
        invoice.cancelled_by_id = user_id
        invoice.cancel_reason = reason

        self._db.commit()
        self._db.refresh(invoice)
        return invoice

    def delete(self, shop_id: int, invoice_id: int) -> None:
        invoice = self._repo.get_by_id_locked(shop_id, invoice_id)
        if not invoice:
            raise InvoiceNotFoundError("Facture introuvable")

        if not invoice.is_cancelled:
            raise InvoiceNotCancelledError(
                "Seule une facture annulée peut être supprimée. Annulez-la d'abord."
            )

        # Les lignes et paiements (déjà annulés puisque cancel() exige
        # amount_paid == 0) sont supprimés en cascade (cascade="all, delete-orphan"
        # sur Invoice.lines / Invoice.payments).
        self._db.delete(invoice)
        self._db.commit()
