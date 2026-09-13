"""add invoice_lines cost_price

Revision ID: a1c8e5f3d9b2
Revises: f2a29791908c
Create Date: 2026-09-10 00:00:00.000000

Capture le coût d'achat (products.purchase_price / purchase_price_secondaire)
au moment de la création de chaque ligne de facture, pour calculer un bénéfice
réel par vente dans le module Statistiques. Nullable et sans server_default :
les lignes historiques restent NULL et sont couvertes par un fallback sur le
purchase_price ACTUEL du produit au moment du calcul des statistiques (voir
app/modules/statistics/statistics_repository.py::_effective_cost_price) plutôt
que par une valeur figée à 0 qui fausserait le bénéfice historique.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c8e5f3d9b2'
down_revision: Union[str, None] = 'f2a29791908c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "invoice_lines",
        sa.Column("cost_price", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invoice_lines", "cost_price")
