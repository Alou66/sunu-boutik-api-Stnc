"""add unique index on clients (shop_id, lower(name))

Revision ID: d3f9a1c5b2e4
Revises: c37c79b4725c
Create Date: 2026-07-30 09:00:00.000000

Empêche deux clients portant le même nom (insensible à la casse) dans une
même boutique, pour que la recherche de factures par nom de client reste
non ambiguë. La vérification applicative dans clients.py
(_ensure_name_available) reste la première ligne de défense (message
d'erreur clair) ; cet index unique est le filet de sécurité en base.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd3f9a1c5b2e4'
down_revision: Union[str, None] = 'c37c79b4725c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX uq_clients_shop_id_lower_name ON clients (shop_id, lower(name))"
    )


def downgrade() -> None:
    op.drop_index("uq_clients_shop_id_lower_name", table_name="clients")
