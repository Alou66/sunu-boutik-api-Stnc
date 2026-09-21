"""Rapport (LECTURE SEULE) des doublons de noms bloquant les index uniques
uq_products_shop_id_upper_name et uq_categories_shop_id_lower_name
(migration e7b1c4d9a2f3).

Usage :
    python scripts/report_duplicate_names.py
    python scripts/report_duplicate_names.py --database-url postgresql://user@host/db

Sans --database-url, la base est celle de DATABASE_URL (variable d'environnement
ou .env). Le script n'exécute que des SELECT et n'écrit rien.

Pour chaque groupe de doublons (même boutique, même nom à la casse près), il
liste chaque ligne avec les données qui la référencent :
  - article    : lignes de facture, lignes de réception, mouvements de stock,
                 historique de transformations, stock actuel ;
  - catégorie  : nombre d'articles rattachés.

Code de sortie : 0 = aucun doublon (la migration peut être appliquée),
1 = des doublons existent.

Ce script ne propose PAS de gagnant et ne modifie aucune donnée : garder l'une
des lignes, fusionner leurs références ou renommer l'autre est une décision
métier à prendre groupe par groupe (voir la docstring de la migration).
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

PRODUCT_DUPLICATES_SQL = """
SELECT p.shop_id, p.id, p.name, p.quantity, p.quantity_secondaire, p.created_at,
       (SELECT count(*) FROM invoice_lines x WHERE x.product_id = p.id) AS invoice_lines,
       (SELECT count(*) FROM stock_receipt_lines x WHERE x.product_id = p.id) AS receipt_lines,
       (SELECT count(*) FROM stock_movements x WHERE x.product_id = p.id) AS stock_movements,
       (SELECT count(*) FROM transformation_logs x WHERE x.product_id = p.id) AS transformation_logs
FROM products p
WHERE (p.shop_id, upper(p.name)) IN (
    SELECT shop_id, upper(name) FROM products GROUP BY shop_id, upper(name) HAVING count(*) > 1
)
ORDER BY p.shop_id, upper(p.name), p.id
"""

CATEGORY_DUPLICATES_SQL = """
SELECT c.shop_id, c.id, c.name, c.created_at,
       (SELECT count(*) FROM products x WHERE x.category_id = c.id) AS products
FROM categories c
WHERE (c.shop_id, lower(c.name)) IN (
    SELECT shop_id, lower(name) FROM categories GROUP BY shop_id, lower(name) HAVING count(*) > 1
)
ORDER BY c.shop_id, lower(c.name), c.id
"""


def _print_groups(title, rows, key, columns):
    print(f"\n=== {title} ===")
    if not rows:
        print("Aucun doublon.")
        return 0
    groups = 0
    current = None
    for row in rows:
        group_key = (row["shop_id"], key(row["name"]))
        if group_key != current:
            current = group_key
            groups += 1
            print(f"\n[boutique {row['shop_id']}] nom normalisé : {group_key[1]!r}")
        details = ", ".join(f"{label}={row[column]}" for column, label in columns)
        print(f"  - id={row['id']} nom={row['name']!r} créé le {row['created_at']} | {details}")
    print(f"\n{groups} groupe(s) de doublons, {len(rows)} ligne(s) concernée(s).")
    return groups


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--database-url", help="Remplace DATABASE_URL (variable d'environnement / .env).")
    args = parser.parse_args()

    if args.database_url:
        url = args.database_url
    else:
        from app.core.config import settings

        url = settings.DATABASE_URL

    engine = create_engine(url)
    target = make_url(url)
    print(f"Base analysée (lecture seule) : {target.host or 'local'}/{target.database}")

    with engine.connect() as conn:
        # Aucune écriture : la transaction est en lecture seule côté Postgres.
        conn.execute(text("SET TRANSACTION READ ONLY"))
        products = [dict(r._mapping) for r in conn.execute(text(PRODUCT_DUPLICATES_SQL))]
        categories = [dict(r._mapping) for r in conn.execute(text(CATEGORY_DUPLICATES_SQL))]

    product_groups = _print_groups(
        "Articles en doublon (index : shop_id, upper(name))",
        products,
        key=lambda name: name.upper(),
        columns=[
            ("quantity", "stock"),
            ("quantity_secondaire", "stock_sec"),
            ("invoice_lines", "lignes_facture"),
            ("receipt_lines", "lignes_reception"),
            ("stock_movements", "mouvements_stock"),
            ("transformation_logs", "transformations"),
        ],
    )
    category_groups = _print_groups(
        "Catégories en doublon (index : shop_id, lower(name))",
        categories,
        key=lambda name: name.lower(),
        columns=[("products", "articles")],
    )

    if product_groups or category_groups:
        print(
            "\nRÉSULTAT : des doublons bloquent la migration e7b1c4d9a2f3. "
            "Décision métier requise pour chaque groupe (garder / fusionner / renommer)."
        )
        return 1
    print("\nRÉSULTAT : aucun doublon, la migration e7b1c4d9a2f3 peut être appliquée.")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    sys.exit(main())
