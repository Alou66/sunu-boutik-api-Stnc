"""add products purchase_price and purchase_price_secondaire

Revision ID: f2a29791908c
Revises: 88dd94437b8c
Create Date: 2026-09-08 00:00:00.000000

Le module Approvisionnement (stock_receipts) préremplissait "Coût U" avec
products.unit_price, qui est le prix de VENTE, pas le prix d'achat fournisseur.
Ajoute un vrai champ purchase_price (forme principale) et purchase_price_secondaire
(forme secondaire, articles transformables) pour que le coût par défaut d'une
réception de stock reflète ce que la boutique paie réellement.
Voir app/modules/products/products_model.py et
app/modules/stock_receipts/stock_receipts_service.py::_build_lines.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a29791908c'
down_revision: Union[str, None] = '88dd94437b8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("purchase_price", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "products",
        sa.Column("purchase_price_secondaire", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "purchase_price_secondaire")
    op.drop_column("products", "purchase_price")
