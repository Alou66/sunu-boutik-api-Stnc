"""add shop status suspended

Revision ID: 095224a50963
Revises: a1c8e5f3d9b2
Create Date: 2026-09-12 00:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "095224a50963"
down_revision = "a1c8e5f3d9b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE ne peut pas s'exécuter dans le bloc transactionnel
    # qu'Alembic ouvre par défaut sur Postgres.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE shopstatus ADD VALUE IF NOT EXISTS 'SUSPENDED'")


def downgrade() -> None:
    # Postgres ne permet pas de retirer une valeur d'ENUM sans recréer le type
    # (et migrer toutes les colonnes qui l'utilisent). Comme cette valeur est
    # purement additive et ne casse aucune donnée existante, le downgrade est
    # volontairement un no-op.
    pass
