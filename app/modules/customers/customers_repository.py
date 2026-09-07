from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.customers.customers_model import Client


class ClientRepository:
    def __init__(self, db: Session):
        self._db = db

    def list_paginated(self, shop_id: int, page: int, page_size: int, search: str | None):
        query = self._db.query(Client).filter(Client.shop_id == shop_id)
        if search:
            query = query.filter((Client.name.ilike(f"%{search}%")) | (Client.phone.ilike(f"%{search}%")))
        total = query.count()
        items = query.order_by(Client.name).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def get_by_id(self, shop_id: int, client_id: int) -> Client | None:
        return self._db.query(Client).filter(Client.id == client_id, Client.shop_id == shop_id).first()

    def exists_with_phone(self, shop_id: int, phone: str, exclude_id: int | None = None) -> bool:
        query = self._db.query(Client).filter(Client.shop_id == shop_id, Client.phone == phone)
        if exclude_id is not None:
            query = query.filter(Client.id != exclude_id)
        return query.first() is not None

    def exists_with_name(self, shop_id: int, name: str, exclude_id: int | None = None) -> bool:
        query = self._db.query(Client).filter(Client.shop_id == shop_id, func.lower(Client.name) == name.lower())
        if exclude_id is not None:
            query = query.filter(Client.id != exclude_id)
        return query.first() is not None

    def save_new(self, client: Client) -> Client:
        self._db.add(client)
        self._db.commit()
        self._db.refresh(client)
        return client

    def save(self, client: Client) -> Client:
        self._db.commit()
        self._db.refresh(client)
        return client

    def delete(self, client: Client) -> None:
        self._db.delete(client)
        self._db.commit()
