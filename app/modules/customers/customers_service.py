from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.customers.customers_model import Client
from app.modules.customers.customers_repository import ClientRepository


class ClientNotFoundError(Exception):
    pass


class ClientValidationError(Exception):
    pass


class DuplicateClientPhoneError(Exception):
    pass


class DuplicateClientNameError(Exception):
    pass


class ClientPhoneConflictError(Exception):
    pass


class ClientConflictError(Exception):
    pass


class ClientInUseError(Exception):
    pass


class ClientService:
    def __init__(self, db: Session):
        self._db = db
        self._repo = ClientRepository(db)

    def list(self, shop_id: int, page: int, page_size: int, search: str | None):
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        return self._repo.list_paginated(shop_id, page, page_size, search)

    def get(self, shop_id: int, client_id: int) -> Client:
        client = self._repo.get_by_id(shop_id, client_id)
        if not client:
            raise ClientNotFoundError("Client introuvable")
        return client

    def create(self, shop_id: int, data: dict) -> Client:
        name = (data.get("name") or "").strip()
        if not name:
            raise ClientValidationError("Le nom du client est requis")
        phone = data.get("phone")
        if phone and self._repo.exists_with_phone(shop_id, phone):
            raise DuplicateClientPhoneError("Un client avec ce numéro de téléphone existe déjà dans cette boutique.")
        if self._repo.exists_with_name(shop_id, name):
            raise DuplicateClientNameError("Un client avec ce nom existe déjà dans cette boutique.")
        # Second contrôle du téléphone, redondant avec celui ci-dessus dans le
        # comportement d'origine (aucun commit entre les deux, donc jamais
        # atteint en pratique) — conservé pour ne rien changer au comportement.
        if phone and self._repo.exists_with_phone(shop_id, phone):
            raise ClientPhoneConflictError("Un client avec ce numéro de téléphone existe déjà")

        client = Client(shop_id=shop_id, name=name, phone=phone, address=data.get("address"))
        self._db.add(client)
        try:
            self._db.commit()
        except IntegrityError:
            self._db.rollback()
            raise ClientConflictError("Un client avec ce nom ou ce numéro de téléphone existe déjà")
        self._db.refresh(client)
        return client

    def update(self, shop_id: int, client_id: int, data: dict) -> Client:
        client = self.get(shop_id, client_id)

        if "name" in data:
            name = (data["name"] or "").strip()
            if not name:
                raise ClientValidationError("Le nom du client est requis")
            data["name"] = name
            if self._repo.exists_with_name(shop_id, name, exclude_id=client.id):
                raise DuplicateClientNameError("Un client avec ce nom existe déjà dans cette boutique.")
        if "phone" in data:
            phone = data["phone"]
            if phone and self._repo.exists_with_phone(shop_id, phone, exclude_id=client.id):
                raise ClientPhoneConflictError("Un client avec ce numéro de téléphone existe déjà")

        for field, value in data.items():
            setattr(client, field, value)
        try:
            self._db.commit()
        except IntegrityError:
            self._db.rollback()
            raise ClientConflictError("Un client avec ce nom ou ce numéro de téléphone existe déjà")
        self._db.refresh(client)
        return client

    def delete(self, shop_id: int, client_id: int) -> None:
        from app.modules.billing.billing_model import Invoice

        client = self.get(shop_id, client_id)
        if self._db.query(Invoice).filter(Invoice.client_id == client_id).first():
            raise ClientInUseError("Impossible de supprimer ce client car il est utilisé dans une ou plusieurs factures.")
        self._repo.delete(client)
