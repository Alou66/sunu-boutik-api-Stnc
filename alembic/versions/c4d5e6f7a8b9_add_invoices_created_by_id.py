"""add invoices created_by_id

Revision ID: c4d5e6f7a8b9
Revises: b3d4e5f6a7c8
Create Date: 2026-09-14 00:00:00.000000

Trace quel utilisateur (employé ou admin) a créé chaque facture, pour
l'affichage dans l'historique des factures et le filtre par employé.
Nullable et sans backfill : les factures existantes restent sans auteur
connu (affichées avec un "—" côté frontend), comme pour
payments.created_by_id et stock_receipts.created_by_id.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3d4e5f6a7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_invoices_created_by_id", "invoices", ["created_by_id"])


def downgrade() -> None:
    op.drop_index("ix_invoices_created_by_id", table_name="invoices")
    op.drop_column("invoices", "created_by_id")
