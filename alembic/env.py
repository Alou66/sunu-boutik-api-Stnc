import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Permet d'importer le package `app` quel que soit le répertoire depuis lequel
# la commande alembic est lancée.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db.session import Base  # noqa: E402

# Chaque import ci-dessous enregistre les tables du module sur Base.metadata
# (nécessaire pour l'autogenerate). Il n'y a plus de module `app.models`
# central depuis le passage à l'architecture par modules : on importe donc
# chaque `*_model.py` directement, comme le fait déjà `app/main.py` de façon
# indirecte via les routers.
from app.modules.identity import identity_model  # noqa: E402,F401
from app.modules.categories import categories_model  # noqa: E402,F401
from app.modules.products import products_model  # noqa: E402,F401
from app.modules.customers import customers_model  # noqa: E402,F401
from app.modules.billing import billing_model  # noqa: E402,F401
from app.modules.payments import payments_model  # noqa: E402,F401
from app.modules.transformations import transformations_model  # noqa: E402,F401
from app.modules.bon_client import bon_client_model  # noqa: E402,F401
from app.modules.suppliers import suppliers_model  # noqa: E402,F401
from app.modules.stock_receipts import stock_receipts_model  # noqa: E402,F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# L'URL vient de app.core.config (donc du .env), pas de alembic.ini, pour
# n'avoir qu'une seule source de vérité pour la connexion DB.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
