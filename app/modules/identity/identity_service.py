from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    generate_reset_code,
    hash_password,
    hash_reset_code,
    verify_password,
    verify_reset_code,
)
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


class InvalidResetCodeError(Exception):
    # Volontairement unique pour : compte inconnu, aucun code actif, code
    # erroné, expiré, déjà utilisé ou épuisé, afin que la réponse ne révèle ni
    # l'existence d'un compte ni l'état de son code.
    pass


class ProfileValidationError(Exception):
    pass


PASSWORD_RESET_CODE_TTL = timedelta(minutes=15)
PASSWORD_RESET_MAX_ATTEMPTS = 5
# Délai minimal entre deux e-mails de code pour un même compte (anti-spam de la
# boîte mail de la victime, en plus du rate limiting par IP de la route).
PASSWORD_RESET_RESEND_COOLDOWN = timedelta(seconds=60)
MIN_PASSWORD_LENGTH = 6


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
        # Coupe toutes les sessions ouvertes avec l'ancien mot de passe (voir
        # core/deps.get_current_user : le claim "tv" des JWT déjà émis ne
        # correspond plus).
        user.token_version += 1
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

    @staticmethod
    def _clear_reset_code(user: User) -> None:
        user.reset_code_hash = None
        user.reset_code_expires_at = None
        user.reset_code_attempts = 0

    def request_password_reset(self, email: str) -> tuple[str, str, str] | None:
        """Génère un code temporaire pour `email` et retourne (nom, e-mail, code) à
        envoyer par e-mail, ou None si rien ne doit être envoyé (compte inconnu,
        inactif, ou code déjà envoyé il y a moins d'une minute).

        Vaut pour tout rôle, y compris ADMIN (l'administrateur de la plateforme) :
        c'est le même compte `users`, avec sa propre connexion (login_admin), mais
        aucune raison de le priver de ce mécanisme s'il oublie son mot de passe.

        L'appelant répond de la même façon dans tous les cas : le code n'est
        jamais retourné à l'utilisateur HTTP, uniquement au code d'envoi d'e-mail.
        """
        user = self._repo.find_user_by_email(email)
        # Comptes inactifs (boutique en attente, rejetée, suspendue, employé
        # désactivé) : ils ne peuvent pas se connecter, donc n'ont rien à
        # réinitialiser.
        if not user or not user.is_active:
            return None

        now = datetime.utcnow()
        if user.reset_code_expires_at:
            issued_at = user.reset_code_expires_at - PASSWORD_RESET_CODE_TTL
            if issued_at + PASSWORD_RESET_RESEND_COOLDOWN > now:
                return None

        code = generate_reset_code()
        user.reset_code_hash = hash_reset_code(user.id, code)
        user.reset_code_expires_at = now + PASSWORD_RESET_CODE_TTL
        user.reset_code_attempts = 0
        full_name, user_email = user.full_name, user.email
        self._db.commit()
        return full_name, user_email, code

    def confirm_password_reset(self, email: str, code: str, new_password: str) -> None:
        # Contrôle de forme avant tout : un mot de passe trop court ne consomme
        # pas le code et ne dit rien sur le compte.
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise ResetPasswordTooShortError(
                f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères"
            )

        user = self._repo.find_user_by_email_locked(email)
        if (
            not user
            or not user.is_active
            or not user.reset_code_hash
            or not user.reset_code_expires_at
        ):
            raise InvalidResetCodeError("Code invalide ou expiré. Demandez un nouveau code.")

        if user.reset_code_expires_at < datetime.utcnow():
            self._clear_reset_code(user)
            self._db.commit()
            raise InvalidResetCodeError("Code invalide ou expiré. Demandez un nouveau code.")

        if not verify_reset_code(user.id, (code or "").strip(), user.reset_code_hash):
            user.reset_code_attempts += 1
            if user.reset_code_attempts >= PASSWORD_RESET_MAX_ATTEMPTS:
                # Code épuisé : il faut en redemander un (réponse identique ensuite).
                self._clear_reset_code(user)
            self._db.commit()
            raise InvalidResetCodeError("Code invalide ou expiré. Demandez un nouveau code.")

        user.hashed_password = hash_password(new_password)
        user.must_change_password = False
        # Coupe toutes les sessions ouvertes avec l'ancien mot de passe (voir
        # core/deps.get_current_user) et consomme le code (usage unique).
        user.token_version += 1
        self._clear_reset_code(user)
        self._db.commit()
