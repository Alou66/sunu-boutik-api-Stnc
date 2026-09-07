"""add product transformation support

Revision ID: f1a2b3c4d5e6
Revises: c37c79b4725c
Create Date: 2026-07-30 10:00:00.000000

- `products` gagne les colonnes de transformation : `is_transformable`,
  `unit_secondaire`, `conversion_ratio`, `unit_price_secondaire`,
  `quantity_secondaire`. `unit` (déjà existant) sert de nom à la forme
  principale et `quantity` (déjà existant) reste le stock de cette forme
  principale — voir app/models/models.py::Product.
- `invoice_lines` gagne `form` (principale/secondaire) pour savoir quel
  compteur de stock créditer si la ligne est modifiée/supprimée.
- Nouvelle table `transformation_logs` : historique des transformations
  effectuées (qui, quand, quelles quantités).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'c37c79b4725c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("is_transformable", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("products", sa.Column("unit_secondaire", sa.String(length=20), nullable=True))
    op.add_column("products", sa.Column("conversion_ratio", sa.Float(), nullable=True))
    op.add_column("products", sa.Column("unit_price_secondaire", sa.Float(), nullable=True))
    op.add_column("products", sa.Column("quantity_secondaire", sa.Float(), nullable=False, server_default="0"))
    op.create_check_constraint(
        "ck_products_transformable_fields",
        "products",
        "NOT is_transformable OR ("
        "unit_secondaire IS NOT NULL AND conversion_ratio > 0 AND unit_price_secondaire >= 0"
        ")",
    )
    op.create_check_constraint(
        "ck_products_quantity_secondaire_non_negative",
        "products",
        "quantity_secondaire >= 0",
    )

    op.add_column("invoice_lines", sa.Column("form", sa.String(length=20), nullable=True))
    op.create_check_constraint(
        "ck_invoice_lines_form",
        "invoice_lines",
        "form IN ('principale', 'secondaire')",
    )

    op.create_table(
        "transformation_logs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id"), nullable=False, index=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column(
            # Les labels de l'ENUM Postgres reprennent le NOM des membres Python
            # (TO_SECONDAIRE / TO_PRINCIPALE), pas leur valeur : c'est ce que
            # SQLAlchemy écrit par défaut pour Column(Enum(PythonEnumClass)),
            # comme pour shopstatus/userrole déjà en base.
            "direction",
            sa.Enum("TO_SECONDAIRE", "TO_PRINCIPALE", name="transformationdirection"),
            nullable=False,
        ),
        sa.Column("unit_from", sa.String(length=20), nullable=False),
        sa.Column("unit_to", sa.String(length=20), nullable=False),
        sa.Column("quantity_from", sa.Float(), nullable=False),
        sa.Column("quantity_to", sa.Float(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_transformation_logs_shop_id_created_at",
        "transformation_logs",
        ["shop_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_transformation_logs_shop_id_created_at", table_name="transformation_logs")
    op.drop_table("transformation_logs")
    sa.Enum(name="transformationdirection").drop(op.get_bind(), checkfirst=True)

    op.drop_constraint("ck_invoice_lines_form", "invoice_lines", type_="check")
    op.drop_column("invoice_lines", "form")

    op.drop_constraint("ck_products_quantity_secondaire_non_negative", "products", type_="check")
    op.drop_constraint("ck_products_transformable_fields", "products", type_="check")
    op.drop_column("products", "quantity_secondaire")
    op.drop_column("products", "unit_price_secondaire")
    op.drop_column("products", "conversion_ratio")
    op.drop_column("products", "unit_secondaire")
    op.drop_column("products", "is_transformable")
