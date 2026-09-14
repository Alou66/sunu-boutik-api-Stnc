from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.core.uploads import save_shop_logo
from app.modules.identity.identity_model import Shop, ShopStatus, User, UserRole
from app.modules.identity.identity_repository import IdentityRepository


class EmailAlreadyUsedError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class ShopPendingError(Exception):
    pass


class ShopRejectedError(Exception):
    pass


class ShopSuspendedError(Exception):
    pass


class AccountDisabledError(Exception):
    pass


class ShopNotFoundError(Exception):
    pass


class CurrentPasswordIncorrectError(Exception):
    pass


class NewPasswordTooShortError(Exception):
    pass


class ResetPasswordTooShortError(Exception):
    pass


class AccountNotFoundByPhoneError(Exception):
    pass


class PhoneNotFoundError(Exception):
    pass


class ProfileValidationError(Exception):
    pass


class IdentityService:
    def __init__(self, db: Session):
        self._db = db
        self._repo = IdentityRepository(db)

    async def register(
        self,
        shop_name: str,
        shop_address: str | None,
        shop_phone: str | None,
        shop_phone2: str | None,
        shop_phone3: str | None,
        shop_ninea: str | None,
        shop_rc: str | None,
        full_name: str,
        email: str,
        logo,
    ) -> tuple[Shop, User]:
        existing = self._repo.find_user_by_email(email)
        if existing:
            raise EmailAlreadyUsedError("Cet email est déjà utilisé")

        shop = Shop(
            name=shop_name,
            address=shop_address,
            phone=shop_phone or None,
            phone2=shop_phone2 or None,
            phone3=shop_phone3 or None,
            ninea=shop_ninea or None,
            rc=shop_rc or None,
            status=ShopStatus.PENDING,
        )
        self._db.add(shop)
        self._db.flush()

        if logo and logo.filename:
            shop.logo_path = await save_shop_logo(shop.id, logo)

        user = User(
            shop_id=shop.id,
            full_name=full_name,
            email=email,
            hashed_password=None,
            is_active=False,
        )
        self._db.add(user)
        self._db.commit()

        return shop, user

    def login(self, email: str, password: str) -> str:
        user = self._repo.find_user_by_email(email)
        if not user or user.role == UserRole.ADMIN:
            # Les comptes admin ne peuvent pas s'authentifier via la connexion boutique.
            raise InvalidCredentialsError("Email ou mot de passe incorrect")

        shop = self._repo.get_shop_by_id(user.shop_id)
        if not shop or shop.status == ShopStatus.PENDING:
            raise ShopPendingError(
                "Votre demande est en cours de traitement. Vous ne pouvez pas encore vous connecter."
            )
        if shop.status == ShopStatus.REJECTED:
            raise ShopRejectedError("Votre demande a été rejetée.")
        if shop.status == ShopStatus.SUSPENDED:
            raise ShopSuspendedError("Votre boutique a été suspendue. Contactez l'administration.")

        if not user.is_active or not user.hashed_password:
            raise AccountDisabledError("Compte désactivé")

        if not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError("Email ou mot de passe incorrect")

        return create_access_token({"sub": str(user.id), "tv": user.token_version})

    def login_admin(self, email: str, password: str) -> str:
        user = self._repo.find_user_by_email(email)
        if not user or user.role != UserRole.ADMIN:
            raise InvalidCredentialsError("Email ou mot de passe incorrect")

        if not user.is_active or not user.hashed_password:
            raise AccountDisabledError("Compte désactivé")

        if not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError("Email ou mot de passe incorrect")

        return create_access_token({"sub": str(user.id), "tv": user.token_version})

    def get_shop_for_user(self, user: User) -> Shop | None:
        if not user.shop_id:
            return None
        return self._repo.get_shop_by_id(user.shop_id)

    def change_password(self, user: User, current_password: str, new_password: str) -> None:
        if not user.hashed_password or not verify_password(current_password, user.hashed_password):
            raise CurrentPasswordIncorrectError("Mot de passe actuel incorrect")
        if len(new_password) < 6:
            raise NewPasswordTooShortError("Le nouveau mot de passe doit contenir au moins 6 caractères")

        user.hashed_password = hash_password(new_password)
        user.must_change_password = False
        self._db.commit()

    def update_profile(self, user: User, data: dict) -> User:
        # Un utilisateur (owner ou employee) modifie ici ses propres informations
        # personnelles. Pour un employee, c'est le seul moyen de les changer :
        # le propriétaire de la boutique ne peut plus le faire à sa place (voir
        # EmployeeService.update, restreint à mot de passe/activation).
        if "full_name" in data:
            if not data["full_name"]:
                raise ProfileValidationError("Le nom complet est requis")
            user.full_name = data["full_name"]

        if "phone" in data:
            if not data["phone"]:
                raise ProfileValidationError("Le téléphone est requis")
            user.phone = data["phone"]

        if "email" in data and data["email"] is not None and data["email"] != user.email:
            existing = self._repo.find_user_by_email(data["email"])
            if existing and existing.id != user.id:
                raise EmailAlreadyUsedError("Cet email est déjà utilisé")
            user.email = data["email"]

        self._db.commit()
        self._db.refresh(user)
        return user

    def update_shop(self, user: User, data: dict) -> Shop:
        shop = self._repo.get_shop_by_id(user.shop_id)
        if not shop:
            raise ShopNotFoundError("Boutique introuvable")
        for field, value in data.items():
            setattr(shop, field, value or None)
        self._db.commit()
        self._db.refresh(shop)
        return shop

    def forgot_password_check(self, phone: str) -> Shop:
        phone = phone.strip()
        shop = self._repo.get_shop_by_phone(phone)
        if not shop:
            raise AccountNotFoundByPhoneError("Aucun compte trouvé avec ce numéro")
        user = self._repo.get_first_user_of_shop(shop.id)
        if not user or not user.is_active:
            raise AccountNotFoundByPhoneError("Aucun compte trouvé avec ce numéro")
        return shop

    def forgot_password_reset(self, phone: str, new_password: str) -> None:
        phone = phone.strip()
        if len(new_password) < 6:
            raise ResetPasswordTooShortError("Le mot de passe doit contenir au moins 6 caractères")
        shop = self._repo.get_shop_by_phone(phone)
        if not shop:
            raise PhoneNotFoundError("Numéro introuvable")
        user = self._repo.get_first_user_of_shop(shop.id)
        if not user or not user.is_active:
            raise PhoneNotFoundError("Numéro introuvable")
        user.hashed_password = hash_password(new_password)
        user.must_change_password = False
        self._db.commit()
