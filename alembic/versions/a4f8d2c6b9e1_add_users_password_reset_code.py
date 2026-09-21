"""add users password reset code columns

Revision ID: a4f8d2c6b9e1
Revises: e7b1c4d9a2f3
Create Date: 2026-09-20 00:00:00.000000

Réinitialisation du mot de passe par e-mail + code temporaire à usage unique
(remplace le flux par numéro de téléphone) : `reset_code_hash` est le HMAC du
code (jamais le code lui-même), `reset_code_expires_at` sa date d'expiration,
`reset_code_attempts` le nombre de codes erronés déjà saisis. Un code consommé,
expiré ou épuisé est remis à NULL. Colonnes sur `users` plutôt qu'une nouvelle
table : un seul code actif par utilisateur suffit et une nouvelle demande
écrase naturellement l'ancien.

Ajout de colonnes nullables (et d'un entier avec valeur par défaut) : aucune
réécriture longue de la table sur Postgres >= 11.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4f8d2c6b9e1'
down_revision: Union[str, None] = 'e7b1c4d9a2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("reset_code_hash", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("reset_code_expires_at", sa.DateTime(), nullable=True))
    op.add_column(
        "users",
        sa.Column("reset_code_attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "reset_code_attempts")
    op.drop_column("users", "reset_code_expires_at")
    op.drop_column("users", "reset_code_hash")
