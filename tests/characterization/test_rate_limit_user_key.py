"""Caractérise la clé de rate limiting par utilisateur préparée pour les futures
routes /sync/* (étape 0.1.9, utilisée à l'étape 4).

Aucune route /sync/* n'existe dans l'application : ces tests montent une
mini-application LOCALE au test, avec son propre Limiter, qui reproduit la
configuration prévue (limite par défaut par IP + une route qui pose sa propre
limite avec key_func=user_or_ip_key). L'application réelle n'est pas modifiée.

Réf. app/core/limiter.py::user_or_ip_key.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from jose import jwt
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.requests import Request as StarletteRequest

from app.core.config import settings
from app.core.limiter import limiter as app_limiter
from app.core.limiter import user_or_ip_key
from app.core.security import create_access_token

SYNC_LIMIT = 3  # requêtes/minute par clé dans la mini-app


def _bearer(user_id):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user_id), 'tv': 0})}"}


def _request(headers=None, client_host="10.0.0.1"):
    return StarletteRequest(
        {
            "type": "http",
            "method": "GET",
            "path": "/sync/ping",
            "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "client": (client_host, 5000),
        }
    )


@pytest.fixture
def sync_client():
    # Même schéma que app.main : limite par défaut par IP (ici 2/minute pour
    # rendre le partage d'IP visible) ; la route /sync/ping pose sa propre limite.
    test_limiter = Limiter(key_func=get_remote_address, default_limits=["2/minute"])
    test_app = FastAPI()
    test_app.state.limiter = test_limiter

    @test_app.exception_handler(RateLimitExceeded)
    def _handler(request: Request, exc: RateLimitExceeded):
        return JSONResponse(status_code=429, content={"detail": "Trop de requêtes"})

    test_app.add_middleware(SlowAPIMiddleware)

    @test_app.get("/sync/ping")
    @test_limiter.limit(f"{SYNC_LIMIT}/minute", key_func=user_or_ip_key)
    def sync_ping(request: Request):
        return {"ok": True}

    @test_app.get("/regular/ping")
    def regular_ping(request: Request):
        return {"ok": True}

    with TestClient(test_app) as c:
        yield c


# ---- La clé elle-même ----


def test_key_is_per_user_when_jwt_is_valid():
    assert user_or_ip_key(_request(_bearer(7))) == "user:7"
    assert user_or_ip_key(_request(_bearer(8))) == "user:8"


def test_key_ignores_ip_for_authenticated_user():
    headers = _bearer(7)
    assert user_or_ip_key(_request(headers, "10.0.0.1")) == user_or_ip_key(_request(headers, "10.0.0.2"))


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer not-a-jwt"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer " + jwt.encode({"sub": "7"}, "mauvaise-cle", algorithm="HS256")},
        {
            "Authorization": "Bearer "
            + jwt.encode(
                {"sub": "7", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                settings.SECRET_KEY,
                algorithm=settings.ALGORITHM,
            )
        },
        {"Authorization": "Bearer " + jwt.encode({"foo": "bar"}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)},
    ],
    ids=["absent", "vide", "non-jwt", "autre-schema", "signature-invalide", "expire", "sans-sub"],
)
def test_key_falls_back_to_ip_when_jwt_is_missing_or_invalid(headers):
    assert user_or_ip_key(_request(headers, "10.0.0.9")) == "10.0.0.9"


# ---- Comportement de limitation ----


def test_two_users_on_same_ip_do_not_share_the_sync_counter(sync_client):
    user_a, user_b = _bearer(1), _bearer(2)

    for _ in range(SYNC_LIMIT):
        assert sync_client.get("/sync/ping", headers=user_a).status_code == 200
    assert sync_client.get("/sync/ping", headers=user_a).status_code == 429  # A a épuisé SON compteur

    # B, même IP, a son propre compteur intact.
    for _ in range(SYNC_LIMIT):
        assert sync_client.get("/sync/ping", headers=user_b).status_code == 200
    assert sync_client.get("/sync/ping", headers=user_b).status_code == 429


def test_same_user_shares_one_counter_across_ips():
    headers = _bearer(1)
    assert user_or_ip_key(_request(headers, "10.0.0.1")) == user_or_ip_key(_request(headers, "192.168.1.5"))


def test_default_limit_by_ip_does_not_apply_to_route_with_its_own_user_key_limit(sync_client):
    # Limite par défaut de la mini-app : 2/minute par IP. La route /sync/ping en
    # accepte SYNC_LIMIT (> 2) pour un même utilisateur : la limite par défaut ne
    # s'y ajoute pas.
    assert SYNC_LIMIT > 2
    for _ in range(SYNC_LIMIT):
        assert sync_client.get("/sync/ping", headers=_bearer(1)).status_code == 200


def test_invalid_tokens_cannot_multiply_counters(sync_client):
    # Un client qui change de faux token à chaque requête reste sur le compteur de son IP.
    statuses = [
        sync_client.get("/sync/ping", headers={"Authorization": f"Bearer faux-{i}"}).status_code
        for i in range(SYNC_LIMIT + 1)
    ]
    assert statuses == [200] * SYNC_LIMIT + [429]


def test_routes_without_user_key_still_share_the_ip_counter(sync_client):
    # Comportement global préservé : sur une route ordinaire (clé IP par
    # défaut), deux utilisateurs de la même IP se partagent le compteur.
    assert sync_client.get("/regular/ping", headers=_bearer(1)).status_code == 200
    assert sync_client.get("/regular/ping", headers=_bearer(2)).status_code == 200
    assert sync_client.get("/regular/ping", headers=_bearer(1)).status_code == 429


# ---- Le limiter global de l'application n'a pas changé ----


def test_global_app_limiter_is_still_keyed_by_ip_with_120_per_minute():
    assert app_limiter._key_func is get_remote_address
    assert [str(limit.limit) for limit in app_limiter._default_limits[0]] == ["120 per 1 minute"]


def test_real_app_login_route_is_still_rate_limited_per_ip(client):
    statuses = [
        client.post("/auth/login", json={"email": "inconnu@example.com", "password": "x"}).status_code
        for _ in range(11)
    ]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
