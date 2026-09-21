import hashlib
import hmac
import secrets
import string
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_PASSWORD_ALPHABET = string.ascii_letters + string.digits


def generate_temp_password(length: int = 10) -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def generate_reset_code(length: int = 6) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def hash_reset_code(user_id: int, code: str) -> str:
    # HMAC-SHA256 avec la clé serveur, lié à l'utilisateur : le code n'est jamais
    # stocké en clair et un hash copié d'un compte ne vaut pas pour un autre.
    # (Un code à 6 chiffres est de faible entropie : la protection contre la force
    # brute repose sur l'expiration courte et le plafond d'essais, voir
    # IdentityService.confirm_password_reset.)
    return hmac.new(
        settings.SECRET_KEY.encode(), f"password-reset:{user_id}:{code}".encode(), hashlib.sha256
    ).hexdigest()


def verify_reset_code(user_id: int, code: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_reset_code(user_id, code), stored_hash)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
