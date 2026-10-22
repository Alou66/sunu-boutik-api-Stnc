"""add stock adjustments

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-10-21 22:35:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stock_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id"), nullable=False, index=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("unit_target", sa.String(length=20), nullable=False),
        sa.Column("adjustment_type", sa.String(length=10), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("quantity_delta", sa.Float(), nullable=False),
        sa.Column("stock_before", sa.Float(), nullable=False),
        sa.Column("stock_after", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_check_constraint(
        "ck_stock_adjustments_type",
        "stock_adjustments",
        "adjustment_type IN ('entry', 'exit')",
    )
    op.create_index(
        "ix_stock_adjustments_shop_id_created_at",
        "stock_adjustments",
        ["shop_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_stock_adjustments_shop_id_created_at", table_name="stock_adjustments")
    op.drop_constraint("ck_stock_adjustments_type", "stock_adjustments", type_="check")
    op.drop_table("stock_adjustments")
