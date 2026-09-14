"""Fixtures pour les tests de caractérisation.

Ces tests figent le comportement ACTUEL du code, avant toute migration
d'architecture (voir le playbook de migration). Ils tournent contre une
base Postgres jetable et locale, distincte de la base de production (Neon) :
les variables d'environnement ci-dessous sont posées avant le premier import
de `app.*` pour que `app.core.config.settings` les lise à la place de `.env`.
"""
import os

os.environ["DATABASE_URL"] = "postgresql://testuser@127.0.0.1:5544/sunu_boutik_test"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ.pop("ADMIN_EMAIL", None)
os.environ.pop("ADMIN_PASSWORD", None)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.limiter import limiter
from app.core.security import create_access_token, hash_password
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.modules.identity.identity_model import Shop, ShopStatus, User, UserRole
from app.modules.categories.categories_model import Category
from app.modules.categories.categories_repository import CategoryRepository
from app.modules.products.products_model import Product
from app.modules.products.products_repository import ProductRepository


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    # `limiter` (slowapi) a un default_limits global partagé par tous les
    # tests du process (même clé : TestClient utilise toujours la même IP
    # factice) : sans reset, des tests sans rapport entre eux peuvent se
    # bloquer les uns les autres en 429 une fois le budget épuisé.
    limiter.reset()
    yield


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def shop(db_session):
    s = Shop(name="Boutique Test", status=ShopStatus.APPROVED)
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


@pytest.fixture
def owner(db_session, shop):
    user = User(
        shop_id=shop.id,
        full_name="Propriétaire Test",
        email="owner@example.com",
        hashed_password=hash_password("Test1234!"),
        role=UserRole.OWNER,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(owner):
    token = create_access_token({"sub": str(owner.id), "tv": owner.token_version})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def employee(db_session, shop):
    user = User(
        shop_id=shop.id,
        full_name="Employé Test",
        email="employee@example.com",
        phone="770000001",
        hashed_password=hash_password("Test1234!"),
        role=UserRole.EMPLOYEE,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def employee_headers(employee):
    token = create_access_token({"sub": str(employee.id), "tv": employee.token_version})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_user(db_session):
    user = User(
        shop_id=None,
        full_name="Admin Test",
        email="admin@example.com",
        hashed_password=hash_password("Test1234!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user):
    token = create_access_token({"sub": str(admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def category(db_session, shop):
    cat = Category(shop_id=shop.id, name="GENERAL")
    db_session.add(cat)
    db_session.commit()
    db_session.refresh(cat)
    return cat


@pytest.fixture
def simple_product(db_session, shop, category):
    p = Product(
        shop_id=shop.id,
        category_id=category.id,
        name="Riz 25kg",
        unit_price=15000,
        quantity=10,
        unit="unite",
        is_transformable=False,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def category_repo(db_session):
    return CategoryRepository(db_session)


@pytest.fixture
def product_repo(db_session):
    return ProductRepository(db_session)


@pytest.fixture
def transformable_product(db_session, shop, category):
    p = Product(
        shop_id=shop.id,
        category_id=category.id,
        name="Chocopain 5kg",
        unit_price=8000,
        quantity=3,
        unit="carton",
        is_transformable=True,
        unit_secondaire="seau",
        conversion_ratio=4,
        unit_price_secondaire=2500,
        quantity_secondaire=0,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p
