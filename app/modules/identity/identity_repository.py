from sqlalchemy.orm import Session

from app.modules.identity.identity_model import Shop, User


class IdentityRepository:
    def __init__(self, db: Session):
        self._db = db

    def find_user_by_email(self, email: str) -> User | None:
        return self._db.query(User).filter(User.email == email).first()

    def get_shop_by_id(self, shop_id: int) -> Shop | None:
        return self._db.query(Shop).filter(Shop.id == shop_id).first()

    def get_shop_by_phone(self, phone: str) -> Shop | None:
        return self._db.query(Shop).filter(Shop.phone == phone).first()

    def get_first_user_of_shop(self, shop_id: int) -> User | None:
        return self._db.query(User).filter(User.shop_id == shop_id).first()
