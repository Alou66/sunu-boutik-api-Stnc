"""add users phone and token_version

Revision ID: b3d4e5f6a7c8
Revises: 095224a50963
Create Date: 2026-09-14 00:00:00.000000

Module Employés : `phone` est le numéro de contact de l'utilisateur (requis
pour un employé, optionnel pour les autres). `token_version` permet de couper
immédiatement les sessions déjà ouvertes quand un compte est désactivé, y
compris pour les JWT stateless déjà émis (voir core/deps.get_current_user) :
il est comparé au claim "tv" du token, et incrémenté à chaque désactivation.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b3d4e5f6a7c8"
down_revision = "095224a50963"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(length=50), nullable=True))
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
    op.drop_column("users", "phone")
