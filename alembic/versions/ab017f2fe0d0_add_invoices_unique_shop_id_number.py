"""add unique constraint on invoices (shop_id, number)

Revision ID: ab017f2fe0d0
Revises: 437c4537d0c1
Create Date: 2026-07-28 09:00:00.000000

La génération du numéro de facture (COUNT()+1 dans invoices.py) est
désormais protégée côté application par un verrou FOR UPDATE sur la ligne
shop, mais cette contrainte UNIQUE reste le filet de sécurité en base : même
en cas de bug applicatif ou de contournement du verrou, PostgreSQL refusera
tout doublon de numéro pour une même boutique.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'ab017f2fe0d0'
down_revision: Union[str, None] = '437c4537d0c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_invoices_shop_id_number",
        "invoices",
        ["shop_id", "number"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_invoices_shop_id_number", "invoices", type_="unique")
