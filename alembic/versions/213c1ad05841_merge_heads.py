"""merge heads

Revision ID: 213c1ad05841
Revises: d3f9a1c5b2e4, f1a2b3c4d5e6
Create Date: 2026-09-07 00:00:00.000000

Fusion pure (aucun changement de schéma) : `d3f9a1c5b2e4` (unicité clients)
et `f1a2b3c4d5e6` (transformation produits) avaient été créées en parallèle
depuis `c37c79b4725c`, ce qui laissait deux heads Alembic non réconciliées.
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = '213c1ad05841'
down_revision: Union[str, Sequence[str], None] = ('d3f9a1c5b2e4', 'f1a2b3c4d5e6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
