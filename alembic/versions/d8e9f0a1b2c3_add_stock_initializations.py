"""add stock initializations

Revision ID: d8e9f0a1b2c3
Revises: a7c8d9e0f1b2
Create Date: 2026-10-21 17:50:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, None] = "a7c8d9e0f1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stock_initializations",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id"), nullable=False, index=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "stock_initialization_lines",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("stock_initialization_id", sa.Integer(), sa.ForeignKey("stock_initializations.id"), nullable=False, index=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id"), nullable=False, index=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("unit_target", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_check_constraint(
        "ck_stock_initialization_lines_unit_target",
        "stock_initialization_lines",
        "unit_target IN ('principale', 'secondaire')",
    )
    op.create_check_constraint(
        "ck_stock_initialization_lines_quantity_positive",
        "stock_initialization_lines",
        "quantity > 0",
    )
    op.create_unique_constraint(
        "uq_stock_initialization_lines_shop_product_unit_target",
        "stock_initialization_lines",
        ["shop_id", "product_id", "unit_target"],
    )
    op.create_index(
        "ix_stock_initialization_lines_shop_id_product_id",
        "stock_initialization_lines",
        ["shop_id", "product_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_stock_initialization_lines_shop_id_product_id", table_name="stock_initialization_lines")
    op.drop_constraint("uq_stock_initialization_lines_shop_product_unit_target", "stock_initialization_lines", type_="unique")
    op.drop_constraint("ck_stock_initialization_lines_quantity_positive", "stock_initialization_lines", type_="check")
    op.drop_constraint("ck_stock_initialization_lines_unit_target", "stock_initialization_lines", type_="check")
    op.drop_table("stock_initialization_lines")
    op.drop_table("stock_initializations")
