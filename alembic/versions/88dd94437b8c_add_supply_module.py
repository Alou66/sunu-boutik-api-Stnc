"""add supply module (suppliers, stock_receipts, stock_receipt_lines, stock_movements)

Revision ID: 88dd94437b8c
Revises: 213c1ad05841
Create Date: 2026-09-07 00:05:00.000000

Module Approvisionnement : remplace la modification directe de
products.quantity/quantity_secondaire (retirée de ProductCreate/ProductUpdate,
voir app/modules/products/products_dto.py) par un document tracé
(StockReceipt + StockReceiptLine) qui, une fois validé, crédite le stock du
produit et écrit une ligne StockMovement (historique), sur le même principe
que transformation_logs pour les transformations.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '88dd94437b8c'
down_revision: Union[str, None] = '213c1ad05841'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id"), nullable=False, index=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "stock_receipts",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id"), nullable=False, index=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=True, index=True),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "VALIDATED", "CANCELLED", name="stockreceiptstatus"),
            nullable=False,
        ),
        sa.Column("total_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("validated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("validated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "stock_receipt_lines",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("stock_receipt_id", sa.Integer(), sa.ForeignKey("stock_receipts.id"), nullable=False, index=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("unit_target", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit_cost", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_stock_receipt_lines_unit_target",
        "stock_receipt_lines",
        "unit_target IN ('principale', 'secondaire')",
    )
    op.create_check_constraint(
        "ck_stock_receipt_lines_quantity_positive",
        "stock_receipt_lines",
        "quantity > 0",
    )
    op.create_check_constraint(
        "ck_stock_receipt_lines_unit_cost_non_negative",
        "stock_receipt_lines",
        "unit_cost >= 0",
    )

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id"), nullable=False, index=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False, server_default="receipt"),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("unit_target", sa.String(length=20), nullable=False),
        sa.Column("quantity_delta", sa.Float(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_stock_movements_shop_id_created_at",
        "stock_movements",
        ["shop_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_stock_movements_shop_id_created_at", table_name="stock_movements")
    op.drop_table("stock_movements")

    op.drop_constraint("ck_stock_receipt_lines_unit_cost_non_negative", "stock_receipt_lines", type_="check")
    op.drop_constraint("ck_stock_receipt_lines_quantity_positive", "stock_receipt_lines", type_="check")
    op.drop_constraint("ck_stock_receipt_lines_unit_target", "stock_receipt_lines", type_="check")
    op.drop_table("stock_receipt_lines")

    op.drop_table("stock_receipts")
    sa.Enum(name="stockreceiptstatus").drop(op.get_bind(), checkfirst=True)

    op.drop_table("suppliers")
