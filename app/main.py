from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.limiter import limiter
from app.core.security import hash_password
from app.db.session import Base, SessionLocal, engine
from app.modules.admin.admin_route import router as admin_router
from app.modules.billing.billing_route import router as billing_router
from app.modules.cashier.cashier_route import router as cashier_router
from app.modules.categories.categories_route import router as categories_router
from app.modules.customers.customers_route import router as customers_router
from app.modules.bon_client.bon_client_route import router as bon_client_router
from app.modules.employees.employees_route import router as employees_router
from app.modules.identity.identity_model import User, UserRole
from app.modules.identity.identity_route import router as identity_router
from app.modules.payments.payments_route import router as payments_router
from app.modules.products.products_route import router as products_router
from app.modules.statistics.statistics_route import router as statistics_router
from app.modules.stock_receipts.stock_receipts_route import router as stock_receipts_router
from app.modules.suppliers.suppliers_route import router as suppliers_router
from app.modules.transformations.transformations_route import router as transformations_router

app = FastAPI(title="Sunu Boutik API")

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Trop de requêtes, veuillez réessayer plus tard."},
    )


# Codes d'erreur Postgres transitoires liés à la concurrence (voir
# https://www.postgresql.org/docs/current/errcodes-appendix.html) : deux
# transactions peuvent, dans de rares cas, se verrouiller mutuellement même en
# respectant un ordre de verrouillage cohérent (ex: verrou explicite FOR
# UPDATE posé sur un produit par une vente, pendant qu'une réception de
# marchandise en cours sur le même produit attend elle aussi ce verrou, la clé
# étrangère de la ligne insérée par chacune re-sollicitant la même ligne
# produit). Postgres détecte le cycle et annule l'une des deux transactions :
# on la restitue au client comme un conflit propre et rejouable, plutôt que de
# laisser remonter une 500 brute.
_RETRYABLE_PG_ERROR_CODES = {
    "40001",  # serialization_failure
    "40P01",  # deadlock_detected
}


@app.exception_handler(OperationalError)
def db_conflict_handler(request: Request, exc: OperationalError):
    pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
    if pgcode not in _RETRYABLE_PG_ERROR_CODES:
        raise exc
    return JSONResponse(
        status_code=409,
        content={"detail": "Conflit d'accès concurrent détecté, veuillez réessayer."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


app.include_router(identity_router)
app.include_router(admin_router)
app.include_router(categories_router)
app.include_router(products_router)
app.include_router(customers_router)
app.include_router(billing_router)
app.include_router(payments_router)
app.include_router(cashier_router)
app.include_router(transformations_router)
app.include_router(bon_client_router)
app.include_router(suppliers_router)
app.include_router(stock_receipts_router)
app.include_router(statistics_router)
app.include_router(employees_router)


def _seed_admin():
    if not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
        return
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == settings.ADMIN_EMAIL).first()
        if existing:
            return
        admin_user = User(
            shop_id=None,
            full_name="Administrateur",
            email=settings.ADMIN_EMAIL,
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin_user)
        db.commit()
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    _seed_admin()


@app.get("/health")
def health():
    return {"status": "ok"}
