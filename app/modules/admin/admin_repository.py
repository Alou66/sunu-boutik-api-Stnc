from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.billing.billing_model import Invoice
from app.modules.customers.customers_model import Client
from app.modules.identity.identity_model import Shop, User, UserRole
from app.modules.products.products_model import Product


class AdminRepository:
    def __init__(self, db: Session):
        self._db = db

    def shop_status_counts(self) -> dict:
        return dict(self._db.query(Shop.status, func.count(Shop.id)).group_by(Shop.status).all())

    def invoice_totals(self) -> tuple[int, float]:
        count, total = self._db.query(func.count(Invoice.id), func.coalesce(func.sum(Invoice.total), 0)).one()
        return count, float(total or 0)

    def owner_of(self, shop: Shop) -> User | None:
        return (
            self._db.query(User)
            .filter(User.shop_id == shop.id, User.role == UserRole.OWNER)
            .order_by(User.id)
            .first()
        )

    def owners_by_shop_id(self, shop_ids: list[int]) -> dict[int, User]:
        if not shop_ids:
            return {}
        owners = (
            self._db.query(User)
            .filter(User.shop_id.in_(shop_ids), User.role == UserRole.OWNER)
            .order_by(User.id)
            .all()
        )
        result: dict[int, User] = {}
        for owner in owners:
            result.setdefault(owner.shop_id, owner)
        return result

    def list_shops_paginated(self, status_filter: str | None, page: int, page_size: int):
        query = self._db.query(Shop)
        if status_filter:
            query = query.filter(Shop.status == status_filter)
        total = query.count()
        shops = (
            query.order_by(Shop.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return shops, total

    def get_shop_by_id(self, shop_id: int) -> Shop | None:
        return self._db.query(Shop).filter(Shop.id == shop_id).first()

    def shop_stats(self, shop_id: int) -> dict:
        products_count = self._db.query(func.count(Product.id)).filter(Product.shop_id == shop_id).scalar_subquery()
        clients_count = self._db.query(func.count(Client.id)).filter(Client.shop_id == shop_id).scalar_subquery()
        users_count = self._db.query(func.count(User.id)).filter(User.shop_id == shop_id).scalar_subquery()
        invoices_count, total_revenue = (
            self._db.query(func.count(Invoice.id), func.coalesce(func.sum(Invoice.total), 0))
            .filter(Invoice.shop_id == shop_id)
            .one()
        )
        products_count, clients_count, users_count = self._db.query(products_count, clients_count, users_count).one()
        return {
            "products_count": products_count,
            "clients_count": clients_count,
            "users_count": users_count,
            "invoices_count": invoices_count,
            "total_revenue": float(total_revenue),
        }

    def activate_other_users(self, shop_id: int, exclude_user_id: int | None) -> None:
        """Active tous les utilisateurs de la boutique sauf `exclude_user_id`
        (le propriétaire, déjà activé séparément par l'appelant)."""
        self._db.query(User).filter(User.shop_id == shop_id, User.id != exclude_user_id).update(
            {User.is_active: True}
        )

    def deactivate_all_users(self, shop_id: int) -> None:
        self._db.query(User).filter(User.shop_id == shop_id).update({User.is_active: False})
