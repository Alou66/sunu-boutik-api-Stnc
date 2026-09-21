"""add unique indexes on products (shop_id, upper(name)) and categories (shop_id, lower(name))

Revision ID: e7b1c4d9a2f3
Revises: 9c1d2e3f4a5b
Create Date: 2026-09-20 00:00:00.000000

Empêche deux articles (insensible à la casse : "Riz", "riz", "RIZ") ou deux
catégories ("Sucre", "sucre", "SUCRE") de porter le même nom dans une même
boutique. Les vérifications applicatives (ProductRepository.exists_with_name,
CategoryRepository.exists_with_name) restent la première ligne de défense
(message d'erreur clair) ; ces index uniques sont le filet de sécurité en base.

PRÉ-REQUIS — aucun doublon historique. Cette migration NE DÉDOUBLONNE RIEN :
choisir quel article ou quelle catégorie garder est une décision métier
(stocks, prix, historique de factures/réceptions/transformations rattachés à
chacun). Si des doublons existent, `upgrade()` s'arrête AVANT toute
modification avec la liste précise des lignes concernées. Pour produire le
même rapport à l'avance (lecture seule, avec le nombre de références par
ligne) :

    python scripts/report_duplicate_names.py

Verrouillage en production : les index sont créés avec CREATE UNIQUE INDEX
CONCURRENTLY (hors transaction, via autocommit_block), qui ne bloque pas les
écritures sur products/categories pendant la construction. Si la construction
échoue (ex: un doublon inséré entre le contrôle ci-dessous et la fin de la
construction), Postgres laisse un index INVALID du même nom : le supprimer
(`DROP INDEX CONCURRENTLY <nom>`) avant de relancer la migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7b1c4d9a2f3'
down_revision: Union[str, None] = '9c1d2e3f4a5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, nom de l'index, expression de normalisation du nom)
_UNIQUE_NAME_INDEXES = (
    ("products", "uq_products_shop_id_upper_name", "upper(name)"),
    ("categories", "uq_categories_shop_id_lower_name", "lower(name)"),
)


def _duplicate_report(bind) -> list[str]:
    lines: list[str] = []
    for table, index_name, expr in _UNIQUE_NAME_INDEXES:
        rows = bind.execute(
            sa.text(
                f"SELECT shop_id, {expr} AS normalized_name, "
                "array_agg(id ORDER BY id) AS ids, array_agg(name ORDER BY id) AS names "
                f"FROM {table} GROUP BY shop_id, {expr} HAVING count(*) > 1 "
                "ORDER BY shop_id, normalized_name"
            )
        ).fetchall()
        for row in rows:
            lines.append(
                f"  - {table}: shop_id={row.shop_id} ids={list(row.ids)} noms={list(row.names)} "
                f"(bloque {index_name})"
            )
    return lines


def upgrade() -> None:
    duplicates = _duplicate_report(op.get_bind())
    if duplicates:
        raise RuntimeError(
            "Migration interrompue, aucune modification effectuée : des doublons de noms existent et "
            "doivent être traités manuellement (décision métier : lequel garder, fusion ou renommage) "
            "avant de créer les index uniques.\n"
            + "\n".join(duplicates)
            + "\nRapport détaillé avec références : python scripts/report_duplicate_names.py"
        )

    with op.get_context().autocommit_block():
        for table, index_name, expr in _UNIQUE_NAME_INDEXES:
            op.create_index(
                index_name,
                table,
                ["shop_id", sa.text(expr)],
                unique=True,
                postgresql_concurrently=True,
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for table, index_name, _expr in reversed(_UNIQUE_NAME_INDEXES):
            op.drop_index(index_name, table_name=table, postgresql_concurrently=True)
