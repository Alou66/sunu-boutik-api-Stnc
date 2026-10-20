"""drop shops.logo_path

Suppression de la colonne logo_path de la table shops : le feature d'upload
et d'affichage de logo de boutique est retiré de l'application (voir le commit
associé). Sur une base existante, cette migration supprime la colonne ; les
fichiers déjà présents sur le système de fichiers (uploads/logos/) devront être
supprimés manuellement si besoin.

Revision ID: a7c8d9e0f1b2
Revises: a4f8d2c6b9e1
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a7c8d9e0f1b2"
down_revision = "a4f8d2c6b9e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("shops", "logo_path")


def downgrade() -> None:
    op.add_column("shops", sa.Column("logo_path", sa.String(length=500), nullable=True))
