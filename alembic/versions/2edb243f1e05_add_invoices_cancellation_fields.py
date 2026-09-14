"""add invoices cancellation fields

Revision ID: 2edb243f1e05
Revises: c4d5e6f7a8b9
Create Date: 2026-09-14 00:00:00.000000

Annulation "douce" des factures (même schéma que payments.voided_at /
void_reason) :
- `cancelled_at` / `cancelled_by_id` : horodatage et auteur de l'annulation.
- `cancel_reason` : motif obligatoire côté API (InvoiceCancelRequest),
  nullable en base car les factures jamais annulées n'en ont pas.

Une facture annulée peut ensuite être supprimée définitivement
(InvoiceService.delete).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2edb243f1e05'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("cancelled_at", sa.DateTime(), nullable=True))
    op.add_column("invoices", sa.Column("cancelled_by_id", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("cancel_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_invoices_cancelled_by_id_users",
        "invoices",
        "users",
        ["cancelled_by_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_invoices_cancelled_by_id_users", "invoices", type_="foreignkey")
    op.drop_column("invoices", "cancel_reason")
    op.drop_column("invoices", "cancelled_by_id")
    op.drop_column("invoices", "cancelled_at")
