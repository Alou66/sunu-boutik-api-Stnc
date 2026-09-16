"""concurrency hardening: idempotency keys + products.quantity check

Revision ID: 9c1d2e3f4a5b
Revises: 2edb243f1e05
Create Date: 2026-09-16 00:00:00.000000

Suite de l'audit concurrence multi-utilisateurs (plusieurs ADMIN/EMPLOYEE
travaillant en même temps sur le stock/les factures/les transformations) :

- `invoices.idempotency_key` / `transformation_logs.idempotency_key` :
  même mécanisme que `payments.idempotency_key` (voir migration
  c37c79b4725c) — un identifiant stable généré côté client par tentative,
  rejoué en cas de double clic / retry réseau, pour ne jamais créer deux
  factures ou appliquer deux fois la même transformation pour une seule
  action utilisateur. Unique par boutique via un index partiel qui ignore
  les valeurs NULL (les soumissions existantes, sans idempotency_key,
  restent valides).
- `ck_products_quantity_non_negative` : la forme secondaire du stock
  (`quantity_secondaire`) avait déjà cette contrainte
  (`ck_products_quantity_secondaire_non_negative`, migration
  f1a2b3c4d5e6) mais pas la forme principale (`quantity`) — trou dans le
  filet de sécurité DB. La vraie protection contre la survente concurrente
  reste le verrou `SELECT ... FOR UPDATE` posé sur la ligne produit avant
  chaque décrément (billing_service.py, transformations_service.py,
  stock_receipts_service.py) ; cette contrainte est le dernier rempart si
  ce verrou était un jour contourné par un bug applicatif.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c1d2e3f4a5b'
down_revision: Union[str, None] = '2edb243f1e05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("idempotency_key", sa.String(length=64), nullable=True))
    op.create_index(
        "uq_invoices_shop_id_idempotency_key",
        "invoices",
        ["shop_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.add_column("transformation_logs", sa.Column("idempotency_key", sa.String(length=64), nullable=True))
    op.create_index(
        "uq_transformation_logs_shop_id_idempotency_key",
        "transformation_logs",
        ["shop_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_check_constraint(
        "ck_products_quantity_non_negative",
        "products",
        "quantity >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_products_quantity_non_negative", "products", type_="check")

    op.drop_index("uq_transformation_logs_shop_id_idempotency_key", table_name="transformation_logs")
    op.drop_column("transformation_logs", "idempotency_key")

    op.drop_index("uq_invoices_shop_id_idempotency_key", table_name="invoices")
    op.drop_column("invoices", "idempotency_key")
