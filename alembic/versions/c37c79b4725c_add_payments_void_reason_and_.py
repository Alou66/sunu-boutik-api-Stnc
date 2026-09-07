"""add payments void_reason and idempotency_key

Revision ID: c37c79b4725c
Revises: ab017f2fe0d0
Create Date: 2026-07-28 09:05:00.000000

- `void_reason` : motif obligatoire (imposé par PaymentVoidRequest côté API)
  saisi lors de l'annulation d'un paiement, pour la traçabilité. Colonne
  nullable en base car les paiements jamais annulés n'en ont pas.
- `idempotency_key` : identifiant fourni par le client pour une tentative
  d'encaissement donnée, afin de rejouer une soumission (double clic, retry
  réseau) sans créer de paiement en double. Unique par boutique via un index
  partiel qui ignore les valeurs NULL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c37c79b4725c'
down_revision: Union[str, None] = 'ab017f2fe0d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("void_reason", sa.Text(), nullable=True))
    op.add_column("payments", sa.Column("idempotency_key", sa.String(length=64), nullable=True))
    op.create_index(
        "uq_payments_shop_id_idempotency_key",
        "payments",
        ["shop_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_payments_shop_id_idempotency_key", table_name="payments")
    op.drop_column("payments", "idempotency_key")
    op.drop_column("payments", "void_reason")
