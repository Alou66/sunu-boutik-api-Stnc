from sqlalchemy.orm import Session

from app.modules.identity.identity_model import Shop, User


class IdentityRepository:
    def __init__(self, db: Session):
        self._db = db

    def find_user_by_email(self, email: str) -> User | None:
        return self._db.query(User).filter(User.email == email).first()

    def find_user_by_email_locked(self, email: str) -> User | None:
        # FOR UPDATE : sérialise les tentatives de confirmation d'un même compte,
        # pour que le compteur d'essais et l'usage unique du code tiennent même
        # sous requêtes concurrentes.
        return self._db.query(User).filter(User.email == email).with_for_update().first()

    def get_shop_by_id(self, shop_id: int) -> Shop | None:
        return self._db.query(Shop).filter(Shop.id == shop_id).first()
