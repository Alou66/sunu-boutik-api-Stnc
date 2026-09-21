from datetime import datetime

from sqlalchemy.orm import Session

from app.core.security import generate_temp_password, hash_password
from app.modules.admin.admin_repository import AdminRepository
from app.modules.identity.identity_model import Shop, ShopStatus, User


class ShopNotFoundError(Exception):
    pass


class InvalidShopStatusError(Exception):
    pass


class OwnerNotFoundError(Exception):
    pass


class AdminService:
    def __init__(self, db: Session):
        self._db = db
        self._repo = AdminRepository(db)

    def overview(self) -> dict:
        status_counts = self._repo.shop_status_counts()
        total_invoices, total_revenue = self._repo.invoice_totals()
        return {
            "total_shops": sum(status_counts.values()),
            "pending_shops": status_counts.get(ShopStatus.PENDING, 0),
            "approved_shops": status_counts.get(ShopStatus.APPROVED, 0),
            "rejected_shops": status_counts.get(ShopStatus.REJECTED, 0),
            "suspended_shops": status_counts.get(ShopStatus.SUSPENDED, 0),
            "total_invoices": total_invoices or 0,
            "total_revenue": total_revenue,
        }

    def list_shops(self, status_filter: str | None, page: int, page_size: int, search: str | None = None):
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        shops, total = self._repo.list_shops_paginated(status_filter, page, page_size, search)
        owners_by_shop = self._repo.owners_by_shop_id([shop.id for shop in shops])
        total_pages = max((total + page_size - 1) // page_size, 1)
        return shops, owners_by_shop, total, page, page_size, total_pages

    def get_shop_with_owner(self, shop_id: int) -> tuple[Shop, User | None]:
        shop = self._repo.get_shop_by_id(shop_id)
        if not shop:
            raise ShopNotFoundError("Boutique introuvable")
        return shop, self._repo.owner_of(shop)

    def shop_stats(self, shop_id: int) -> dict:
        shop = self._repo.get_shop_by_id(shop_id)
        if not shop:
            raise ShopNotFoundError("Boutique introuvable")
        stats = self._repo.shop_stats(shop_id)
        return {
            "shop_id": shop.id,
            "shop_name": shop.name,
            "status": shop.status,
            **stats,
        }

    def approve_shop(self, shop_id: int) -> tuple[Shop, User | None, str | None]:
        shop = self._repo.get_shop_by_id(shop_id)
        if not shop:
            raise ShopNotFoundError("Boutique introuvable")

        shop.status = ShopStatus.APPROVED
        shop.reviewed_at = datetime.utcnow()

        owner = self._repo.owner_of(shop)
        temp_password = generate_temp_password()
        if owner:
            owner.hashed_password = hash_password(temp_password)
            owner.must_change_password = True
            owner.is_active = True

        self._repo.activate_other_users(shop_id, owner.id if owner else None)
        self._db.commit()

        return shop, owner, temp_password if owner else None

    def reject_shop(self, shop_id: int) -> tuple[Shop, User | None]:
        shop = self._repo.get_shop_by_id(shop_id)
        if not shop:
            raise ShopNotFoundError("Boutique introuvable")

        shop.status = ShopStatus.REJECTED
        shop.reviewed_at = datetime.utcnow()
        self._repo.deactivate_all_users(shop_id)
        self._db.commit()

        owner = self._repo.owner_of(shop)
        return shop, owner

    def suspend_shop(self, shop_id: int, reason: str | None) -> tuple[Shop, User | None]:
        shop = self._repo.get_shop_by_id(shop_id)
        if not shop:
            raise ShopNotFoundError("Boutique introuvable")
        if shop.status != ShopStatus.APPROVED:
            raise InvalidShopStatusError("Seule une boutique validée peut être suspendue")

        shop.status = ShopStatus.SUSPENDED
        self._repo.deactivate_all_users(shop_id)
        self._db.commit()

        owner = self._repo.owner_of(shop)
        return shop, owner

    def reactivate_shop(self, shop_id: int) -> tuple[Shop, User | None]:
        shop = self._repo.get_shop_by_id(shop_id)
        if not shop:
            raise ShopNotFoundError("Boutique introuvable")
        if shop.status != ShopStatus.SUSPENDED:
            raise InvalidShopStatusError("Seule une boutique suspendue peut être réactivée")

        shop.status = ShopStatus.APPROVED
        self._repo.activate_other_users(shop_id, None)
        self._db.commit()

        owner = self._repo.owner_of(shop)
        return shop, owner

    def reset_owner_password(self, shop_id: int) -> tuple[Shop, User, str]:
        shop = self._repo.get_shop_by_id(shop_id)
        if not shop:
            raise ShopNotFoundError("Boutique introuvable")

        owner = self._repo.owner_of(shop)
        if not owner or not owner.hashed_password:
            raise OwnerNotFoundError("Cette boutique n'a pas encore de propriétaire actif")

        temp_password = generate_temp_password()
        owner.hashed_password = hash_password(temp_password)
        owner.must_change_password = True
        owner.token_version += 1
        self._db.commit()

        return shop, owner, temp_password
