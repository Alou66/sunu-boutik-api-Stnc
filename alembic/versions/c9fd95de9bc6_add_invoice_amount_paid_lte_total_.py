"""add invoice amount_paid <= total check constraint

Revision ID: c9fd95de9bc6
Revises: 5a34a2f71e8e
Create Date: 2026-07-27 20:00:00.000000

Ceinture de sécurité côté base de données : `amount_paid` ne doit jamais
dépasser `total`, même en cas de bug applicatif. La protection principale
contre les accès concurrents reste le verrou `SELECT ... FOR UPDATE` posé
dans `app/routers/payments.py`, cette contrainte est un dernier filet.

Une tolérance de 0.01 est utilisée pour ne pas rejeter des écarts
d'arrondi flottants (alignée sur `AMOUNT_EPSILON` dans app/models/models.py).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c9fd95de9bc6'
down_revision: Union[str, None] = '5a34a2f71e8e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_invoices_amount_paid_lte_total",
        "invoices",
        "amount_paid <= total + 0.01",
    )


def downgrade() -> None:
    op.drop_constraint("ck_invoices_amount_paid_lte_total", "invoices", type_="check")
