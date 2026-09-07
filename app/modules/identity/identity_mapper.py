from app.modules.identity.identity_dto import MeOut, ShopOut, UserOut
from app.modules.identity.identity_model import Shop, User


def to_user_out(user: User) -> UserOut:
    return UserOut.model_validate(user)


def to_shop_out(shop: Shop) -> ShopOut:
    return ShopOut.model_validate(shop)


def to_me_out(user: User, shop: Shop | None) -> MeOut:
    return MeOut(user=to_user_out(user), shop=to_shop_out(shop) if shop else None)
