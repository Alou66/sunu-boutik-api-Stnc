from app.modules.admin.admin_dto import ShopAdminOut
from app.modules.identity.identity_model import Shop, User


def to_shop_admin_out(shop: Shop, owner: User | None) -> ShopAdminOut:
    return ShopAdminOut(
        id=shop.id,
        name=shop.name,
        address=shop.address,
        phone=shop.phone,
        status=shop.status,
        created_at=shop.created_at,
        reviewed_at=shop.reviewed_at,
        owner_email=owner.email if owner else None,
        owner_name=owner.full_name if owner else None,
    )
