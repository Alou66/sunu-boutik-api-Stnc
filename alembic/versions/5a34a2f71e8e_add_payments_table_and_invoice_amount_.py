"""add payments table and invoice amount_paid

Revision ID: 5a34a2f71e8e
Revises:
Create Date: 2026-07-27 19:02:45.308501

Cette migration est la première du projet : jusqu'ici le schéma était
entièrement géré par Base.metadata.create_all() au démarrage de l'API.
create_all() continue de fonctionner pour les tables qui n'existent pas
encore (il créera donc `payments` tout seul sur une base fraîche), mais il
n'altère jamais une table déjà existante — d'où le besoin d'une vraie
migration pour ajouter la colonne `amount_paid` à `invoices`.

Déploiement :
- Base de données déjà existante (invoices déjà créée par create_all) :
  lancer `alembic upgrade head` directement, cette migration ajoute
  uniquement ce qui manque (colonne + table).
- Base de données neuve : soit démarrer l'API une fois (create_all crée tout
  le schéma à jour, `amount_paid` inclus) puis `alembic stamp head`, soit
  lancer `alembic upgrade head` sur une base où les tables `shops`, `users`,
  `clients`, `invoices`, etc. existent déjà (cette migration ne les recrée
  pas, seul `payments` est nouveau).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a34a2f71e8e'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column(
            "amount_paid",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "ck_invoices_amount_paid_non_negative",
        "invoices",
        "amount_paid >= 0",
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("amount_received", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("voided_at", sa.DateTime(), nullable=True),
        sa.Column("voided_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.CheckConstraint(
            "amount_received IS NULL OR amount_received >= amount",
            name="ck_payments_received_gte_amount",
        ),
    )
    op.create_index("ix_payments_shop_id", "payments", ["shop_id"])
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])
    op.create_index("ix_payments_created_by_id", "payments", ["created_by_id"])
    op.create_index("ix_payments_shop_id_created_at", "payments", ["shop_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_payments_shop_id_created_at", table_name="payments")
    op.drop_index("ix_payments_created_by_id", table_name="payments")
    op.drop_index("ix_payments_invoice_id", table_name="payments")
    op.drop_index("ix_payments_shop_id", table_name="payments")
    op.drop_table("payments")

    op.drop_constraint("ck_invoices_amount_paid_non_negative", "invoices", type_="check")
    op.drop_column("invoices", "amount_paid")
