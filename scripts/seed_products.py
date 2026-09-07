"""Seede une boutique avec des produits de test (simples + transformables),
pour vérifier la pagination et les écrans de transformation de stock.

Usage :
    python scripts/seed_products.py --shop-id 2
    python scripts/seed_products.py --shop-id 2 --simple-count 150 --transformable-count 120
    python scripts/seed_products.py --shop-id 2 --dry-run
    python scripts/seed_products.py --shop-id 2 --delete-seed   # nettoyage

Idempotent : les produits déjà présents (même nom, même boutique) ne sont pas
recréés, donc on peut relancer la commande avec des comptes plus grands pour
compléter. Les produits créés par ce script portent une référence "SEED-xxx",
ce qui permet de les supprimer proprement avec --delete-seed sans toucher aux
vrais produits de la boutique.
"""

import argparse
import random
import sys
import unicodedata
from itertools import cycle
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.main  # noqa: E402  (enregistre tous les modèles pour résoudre les relationships())
from app.db.session import SessionLocal  # noqa: E402
from app.modules.categories.categories_model import Category  # noqa: E402
from app.modules.identity.identity_model import Shop  # noqa: E402
from app.modules.products.products_model import Product  # noqa: E402

# ---------------------------------------------------------------------------
# Catalogue "simple" (non transformable) : couvre tout l'alphabet, le bug
# original faisait disparaître les produits commençant par les dernières
# lettres (ex. "Z") à cause d'une pagination cassée.
# ---------------------------------------------------------------------------
SIMPLE_CATALOG = [
    {"name": "Ananas", "unit": "kg"}, {"name": "Avocat", "unit": "kg"},
    {"name": "Ail", "unit": "kg"}, {"name": "Arachide grillée", "unit": "kg"},
    {"name": "Beignets", "unit": "unite"}, {"name": "Beurre de karité", "unit": "unite"},
    {"name": "Biscuits", "unit": "unite"}, {"name": "Café Touba", "unit": "unite"},
    {"name": "Carotte", "unit": "kg"}, {"name": "Chocolat en poudre", "unit": "unite"},
    {"name": "Dattes", "unit": "kg"}, {"name": "Détergent", "unit": "unite"},
    {"name": "Dentifrice", "unit": "unite"}, {"name": "Eau minérale 1.5L", "unit": "unite"},
    {"name": "Épices mélangées", "unit": "unite"}, {"name": "Éponge", "unit": "unite"},
    {"name": "Farine de blé", "unit": "kg"}, {"name": "Fromage", "unit": "unite"},
    {"name": "Fruit de la passion", "unit": "kg"}, {"name": "Gombo", "unit": "kg"},
    {"name": "Gingembre", "unit": "kg"}, {"name": "Gel douche", "unit": "unite"},
    {"name": "Haricot", "unit": "kg"}, {"name": "Harissa", "unit": "unite"},
    {"name": "Igname", "unit": "kg"}, {"name": "Insecticide", "unit": "unite"},
    {"name": "Jus de bissap", "unit": "unite"}, {"name": "Jus de gingembre", "unit": "unite"},
    {"name": "Jus de bouye", "unit": "unite"}, {"name": "Ketchup", "unit": "unite"},
    {"name": "Kinkeliba", "unit": "unite"}, {"name": "Lait en poudre", "unit": "unite"},
    {"name": "Lentilles", "unit": "kg"}, {"name": "Lessive en poudre", "unit": "unite"},
    {"name": "Mangue", "unit": "kg"}, {"name": "Maïs", "unit": "kg"},
    {"name": "Mayonnaise", "unit": "unite"}, {"name": "Nescafé", "unit": "unite"},
    {"name": "Noix de coco", "unit": "unite"}, {"name": "Nouilles instantanées", "unit": "unite"},
    {"name": "Oignon", "unit": "kg"}, {"name": "Œufs", "unit": "unite"},
    {"name": "Olives", "unit": "unite"}, {"name": "Pain de sucre", "unit": "unite"},
    {"name": "Pâtes alimentaires", "unit": "unite"}, {"name": "Piment", "unit": "kg"},
    {"name": "Quinoa", "unit": "kg"}, {"name": "Riz brisé", "unit": "kg"},
    {"name": "Riz parfumé", "unit": "kg"}, {"name": "Rasoir", "unit": "unite"},
    {"name": "Savon de Marseille", "unit": "unite"}, {"name": "Sac de sucre", "unit": "kg"},
    {"name": "Sel fin", "unit": "kg"}, {"name": "Thé Lipton", "unit": "unite"},
    {"name": "Tomate fraîche", "unit": "kg"}, {"name": "Tomate en boîte", "unit": "unite"},
    {"name": "Umeboxi (prune salée)", "unit": "unite"}, {"name": "Vinaigre", "unit": "unite"},
    {"name": "Vermicelle", "unit": "unite"}, {"name": "Wax imprimé", "unit": "unite"},
    {"name": "Xylitol (édulcorant)", "unit": "unite"}, {"name": "Yaourt nature", "unit": "unite"},
    {"name": "Yassa mix (épices)", "unit": "unite"}, {"name": "Zeste de citron", "unit": "unite"},
    {"name": "Zébu séché (viande)", "unit": "kg"},
]
SIMPLE_VARIANTS = [
    "250g", "500g", "1kg", "2kg", "5kg", "10kg", "25kg",
    "Petit format", "Format familial", "Pack x6", "Pack x12", "Import", "Local",
]

# ---------------------------------------------------------------------------
# Catalogue "transformable" : la forme principale (ex. carton, sac, bidon)
# se transforme en forme secondaire (ex. unité, kg, L) — voir la
# CheckConstraint ck_products_transformable_fields dans products_model.py.
# ---------------------------------------------------------------------------
TRANSFORMABLE_CATALOG = [
    {"name": "Œufs en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 30, "price": (2000, 4000), "price_secondaire": (100, 180)},
    {"name": "Riz brisé en sac", "unit": "sac", "unit_secondaire": "kg", "ratio": 50, "price": (15000, 25000), "price_secondaire": (400, 600)},
    {"name": "Riz parfumé en sac", "unit": "sac", "unit_secondaire": "kg", "ratio": 25, "price": (18000, 30000), "price_secondaire": (900, 1300)},
    {"name": "Sucre en sac", "unit": "sac", "unit_secondaire": "kg", "ratio": 50, "price": (20000, 28000), "price_secondaire": (500, 650)},
    {"name": "Savon en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 24, "price": (6000, 12000), "price_secondaire": (300, 550)},
    {"name": "Lait en poudre en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 48, "price": (15000, 25000), "price_secondaire": (350, 600)},
    {"name": "Huile d'arachide en bidon", "unit": "bidon", "unit_secondaire": "L", "ratio": 20, "price": (12000, 20000), "price_secondaire": (700, 1100)},
    {"name": "Biscuits en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 40, "price": (8000, 15000), "price_secondaire": (250, 450)},
    {"name": "Boisson gazeuse en casier", "unit": "casier", "unit_secondaire": "unite", "ratio": 24, "price": (3000, 6000), "price_secondaire": (150, 300)},
    {"name": "Eau minérale en pack", "unit": "pack", "unit_secondaire": "unite", "ratio": 12, "price": (1500, 3000), "price_secondaire": (150, 300)},
    {"name": "Charbon en sac", "unit": "sac", "unit_secondaire": "kg", "ratio": 50, "price": (5000, 9000), "price_secondaire": (120, 220)},
    {"name": "Farine de blé en sac", "unit": "sac", "unit_secondaire": "kg", "ratio": 50, "price": (15000, 22000), "price_secondaire": (350, 500)},
    {"name": "Tomate en boîte en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 50, "price": (7000, 12000), "price_secondaire": (175, 300)},
    {"name": "Lessive en poudre en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 20, "price": (10000, 18000), "price_secondaire": (600, 1000)},
    {"name": "Thé en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 100, "price": (5000, 9000), "price_secondaire": (60, 120)},
    {"name": "Nescafé en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 48, "price": (20000, 35000), "price_secondaire": (500, 850)},
    {"name": "Pâtes alimentaires en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 30, "price": (9000, 15000), "price_secondaire": (350, 550)},
    {"name": "Concentré de tomate en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 50, "price": (7000, 13000), "price_secondaire": (175, 300)},
    {"name": "Mayonnaise en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 24, "price": (12000, 20000), "price_secondaire": (600, 950)},
    {"name": "Jus de fruit en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 24, "price": (7000, 13000), "price_secondaire": (350, 600)},
    {"name": "Sel fin en sac", "unit": "sac", "unit_secondaire": "kg", "ratio": 25, "price": (4000, 7000), "price_secondaire": (200, 320)},
    {"name": "Lentilles en sac", "unit": "sac", "unit_secondaire": "kg", "ratio": 25, "price": (12000, 18000), "price_secondaire": (550, 800)},
    {"name": "Haricot en sac", "unit": "sac", "unit_secondaire": "kg", "ratio": 50, "price": (20000, 30000), "price_secondaire": (450, 650)},
    {"name": "Maïs en sac", "unit": "sac", "unit_secondaire": "kg", "ratio": 50, "price": (12000, 18000), "price_secondaire": (280, 420)},
    {"name": "Détergent en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 12, "price": (9000, 15000), "price_secondaire": (800, 1300)},
    {"name": "Bougies en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 100, "price": (5000, 9000), "price_secondaire": (60, 100)},
    {"name": "Allumettes en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 50, "price": (2000, 4000), "price_secondaire": (50, 90)},
    {"name": "Papier hygiénique en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 40, "price": (8000, 14000), "price_secondaire": (250, 400)},
    {"name": "Couches bébé en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 30, "price": (15000, 25000), "price_secondaire": (600, 950)},
    {"name": "Chips en carton", "unit": "carton", "unit_secondaire": "unite", "ratio": 24, "price": (6000, 10000), "price_secondaire": (300, 500)},
]
TRANSFORMABLE_VARIANTS = [
    "Import", "Local", "Format standard", "Grand format", "Petit format",
    "Premium", "Économique", "Nouvelle formule", "Édition spéciale",
]

DEFAULT_CATEGORY_NAMES = ["Épicerie", "Boissons", "Hygiène", "Fruits & Légumes", "Autres"]

SEED_REFERENCE_PREFIX = "SEED-"


def sort_key(name: str) -> str:
    """Clé de tri qui ignore les accents, uniquement pour l'aperçu console."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()


def build_candidates(catalog: list[dict], variants: list[str], target_count: int) -> list[tuple[str, dict]]:
    """Génère des (nom_unique, entrée_catalogue) en combinant chaque article de
    base avec des variantes, jusqu'à atteindre target_count ou épuiser le
    produit cartésien catalogue×variantes (dont la taille est bornée, donc pas
    de boucle infinie même quand pgcd(len(catalog), len(variants)) > 1)."""
    result: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for entry in catalog:
        if entry["name"] not in seen:
            seen.add(entry["name"])
            result.append((entry["name"], entry))
    if len(result) < target_count:
        combos = [(entry, variant) for entry in catalog for variant in variants]
        random.shuffle(combos)
        for entry, variant in combos:
            if len(result) >= target_count:
                break
            name = f"{entry['name']} {variant}"
            if name not in seen:
                seen.add(name)
                result.append((name, entry))
    return result


def ensure_categories(db, shop_id: int) -> list[Category]:
    existing = db.query(Category).filter(Category.shop_id == shop_id).all()
    by_name = {c.name: c for c in existing}
    categories = list(existing)
    for name in DEFAULT_CATEGORY_NAMES:
        if name not in by_name:
            cat = Category(shop_id=shop_id, name=name)
            db.add(cat)
            categories.append(cat)
            by_name[name] = cat
    if categories:
        db.flush()  # attribue les IDs sans committer
    return categories


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shop-id", type=int, required=True, help="ID de la boutique à seeder")
    parser.add_argument("--simple-count", type=int, default=120, help="Nombre d'articles simples visé (défaut: 120)")
    parser.add_argument("--transformable-count", type=int, default=150, help="Nombre d'articles transformables visé (défaut: 150)")
    parser.add_argument("--dry-run", action="store_true", help="N'insère rien, affiche seulement ce qui serait fait")
    parser.add_argument("--delete-seed", action="store_true", help="Supprime les produits créés par ce script (référence SEED-*) pour cette boutique")
    parser.add_argument("--seed", type=int, default=42, help="Graine aléatoire pour des données reproductibles")
    args = parser.parse_args()

    random.seed(args.seed)
    db = SessionLocal()
    try:
        shop = db.query(Shop).filter(Shop.id == args.shop_id).first()
        if not shop:
            print(f"Boutique {args.shop_id} introuvable.")
            sys.exit(1)

        if args.delete_seed:
            to_delete = (
                db.query(Product)
                .filter(Product.shop_id == args.shop_id, Product.reference.like(f"{SEED_REFERENCE_PREFIX}%"))
                .all()
            )
            print(f"{len(to_delete)} produit(s) de seed à supprimer pour '{shop.name}' (id={shop.id}).")
            if not args.dry_run:
                for p in to_delete:
                    db.delete(p)
                db.commit()
                print("Supprimé.")
            return

        existing_names = {
            n for (n,) in db.query(Product.name).filter(Product.shop_id == args.shop_id).all()
        }

        simple_candidates = build_candidates(SIMPLE_CATALOG, SIMPLE_VARIANTS, args.simple_count)
        transformable_candidates = build_candidates(TRANSFORMABLE_CATALOG, TRANSFORMABLE_VARIANTS, args.transformable_count)

        simple_to_create = [c for c in simple_candidates if c[0] not in existing_names][: args.simple_count]
        transformable_to_create = [c for c in transformable_candidates if c[0] not in existing_names][: args.transformable_count]

        if not simple_to_create and not transformable_to_create:
            print(f"'{shop.name}' (id={shop.id}) a déjà atteint les cibles demandées. Rien à faire.")
            return

        categories = ensure_categories(db, args.shop_id)
        cat_cycle = cycle(categories)

        print(f"Boutique : {shop.name} (id={shop.id})")
        print(f"Articles simples à créer        : {len(simple_to_create)}")
        print(f"Articles transformables à créer  : {len(transformable_to_create)}")
        print(f"Catégories utilisées : {[c.name for c in categories]}")

        if args.dry_run:
            print("\n--dry-run : aperçu (5 premiers / 5 derniers, tri alphabétique) :")
            for label, items in (("simples", simple_to_create), ("transformables", transformable_to_create)):
                preview = sorted((n for n, _ in items), key=sort_key)
                print(f"  -- {label} --")
                for n in preview[:5]:
                    print(f"    A→ {n}")
                for n in preview[-5:]:
                    print(f"    Z→ {n}")
            return

        ref_counter = 1
        for name, entry in simple_to_create:
            category = next(cat_cycle)
            pack_size = random.choice([1, 1, 1, 6, 12, 24])  # ~50% avec conditionnement carton
            db.add(Product(
                shop_id=args.shop_id,
                category_id=category.id,
                name=name,
                reference=f"{SEED_REFERENCE_PREFIX}{ref_counter:04d}",
                unit_price=float(random.randint(50, 25000) // 25 * 25),
                quantity=float(random.randint(0, 300)),
                unit=entry["unit"],
                pack_size=pack_size,
            ))
            ref_counter += 1

        for name, entry in transformable_to_create:
            category = next(cat_cycle)
            price_min, price_max = entry["price"]
            price_sec_min, price_sec_max = entry["price_secondaire"]
            # ~40% des articles ont déjà une partie transformée en stock, pour
            # refléter une boutique avec de l'activité réelle plutôt qu'un état
            # figé "jamais transformé".
            quantity_secondaire = float(random.randint(0, entry["ratio"] * 2)) if random.random() < 0.4 else 0.0
            db.add(Product(
                shop_id=args.shop_id,
                category_id=category.id,
                name=name,
                reference=f"{SEED_REFERENCE_PREFIX}{ref_counter:04d}",
                unit_price=float(random.randint(price_min, price_max) // 50 * 50),
                quantity=float(random.randint(0, 60)),
                unit=entry["unit"],
                pack_size=1,
                is_transformable=True,
                unit_secondaire=entry["unit_secondaire"],
                conversion_ratio=float(entry["ratio"]),
                unit_price_secondaire=float(random.randint(price_sec_min, price_sec_max) // 5 * 5),
                quantity_secondaire=quantity_secondaire,
            ))
            ref_counter += 1

        db.commit()
        total_now = db.query(Product).filter(Product.shop_id == args.shop_id).count()
        transformable_now = db.query(Product).filter(
            Product.shop_id == args.shop_id, Product.is_transformable.is_(True)
        ).count()
        print(
            f"\n{len(simple_to_create) + len(transformable_to_create)} produit(s) créé(s). "
            f"Total désormais pour la boutique : {total_now} (dont {transformable_now} transformables)."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
