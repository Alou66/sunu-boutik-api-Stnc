"""add composite index on invoices (shop_id, created_at)

Revision ID: 437c4537d0c1
Revises: c9fd95de9bc6
Create Date: 2026-07-27 21:00:00.000000

Les statistiques de caisse journalières (app/routers/caisse.py) et la liste
des factures (app/routers/invoices.py) filtrent systématiquement par
`shop_id` puis par une plage sur `created_at`. Seul `shop_id` était indexé
jusqu'ici ; cet index composite permet à PostgreSQL de servir les deux
prédicats en un seul parcours d'index au lieu de scanner toutes les
factures de la boutique puis de filtrer par date en mémoire.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '437c4537d0c1'
down_revision: Union[str, None] = 'c9fd95de9bc6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_invoices_shop_id_created_at",
        "invoices",
        ["shop_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_invoices_shop_id_created_at", table_name="invoices")
