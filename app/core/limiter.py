from fastapi import Request
from jose import JWTError
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.security import decode_access_token

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


def user_or_ip_key(request: Request) -> str:
    """Clé de limitation par utilisateur authentifié, avec repli sur l'IP.

    PRÉPARATION de l'étape 4 (routes /sync/*, PowerSync) : aucune route ne
    l'utilise encore, et le limiter global ci-dessus (clé = IP, 120/minute)
    est inchangé pour toutes les routes existantes.

    Pourquoi : plusieurs appareils d'une même boutique sortent souvent par la
    même IP (Wi-Fi de la boutique, NAT opérateur). Avec une clé par IP, leurs
    synchronisations se partageraient un seul compteur et se bloqueraient
    mutuellement. Avec cette clé, chaque utilisateur a son propre compteur
    (`user:<id>`), quelle que soit l'IP.

    Le JWT est vérifié (signature + expiration, comme core/deps.get_current_user)
    mais SANS accès base de données : un token forgé, expiré ou absent retombe
    sur la clé IP, donc un client ne peut pas obtenir de compteurs séparés en
    envoyant des tokens invalides.

    Usage prévu à l'étape 4 (une route qui pose sa propre limite avec key_func
    remplace la limite par défaut par IP dans slowapi, override_defaults=True ;
    pas besoin de @limiter.exempt) :

        @router.post("/sync/upload")
        @limiter.limit("60/minute", key_func=user_or_ip_key)
        def sync_upload(request: Request, ...): ...
    """
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            user_id = decode_access_token(token).get("sub")
        except JWTError:
            user_id = None
        if user_id is not None:
            return f"user:{user_id}"
    return get_remote_address(request)
