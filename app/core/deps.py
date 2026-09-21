from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.modules.identity.identity_model import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Identifiants invalides",
        headers={"WWW-Authenticate": "Bearer"},
    )
    disabled_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Compte désactivé. Contactez l'administrateur.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    session_revoked_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Votre session n'est plus valide, veuillez vous reconnecter.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    # Le compte a pu être désactivé (ou réactivé après une désactivation) depuis
    # l'émission de ce token : on revérifie l'état actuel en base à chaque requête
    # plutôt qu'une seule fois au login, et on rejette les tokens émis avant la
    # dernière désactivation même si le compte est de nouveau actif.
    if not user.is_active:
        raise disabled_exception
    # Compte actif mais token_version différent : mot de passe changé ou
    # réinitialisé, ou compte désactivé puis réactivé, depuis l'émission du token.
    # Ce n'est pas une désactivation : message distinct pour que le client
    # n'affiche pas « compte désactivé » à un utilisateur qui doit seulement se
    # reconnecter.
    if payload.get("tv", 0) != user.token_version:
        raise session_revoked_exception
    return user


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès réservé à l'administrateur")
    return current_user


def get_current_owner(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.OWNER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès réservé au propriétaire de la boutique")
    return current_user
