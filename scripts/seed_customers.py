"""Seede une boutique avec des clients de test, pour vérifier la pagination
et les écrans clients/factures avec un volume réaliste.

Usage :
    python scripts/seed_customers.py --shop-id 2
    python scripts/seed_customers.py --shop-id 2 --count 150
    python scripts/seed_customers.py --shop-id 2 --dry-run
    python scripts/seed_customers.py --shop-id 2 --delete-seed   # nettoyage

Idempotent : les clients déjà présents (même nom, même boutique — la table a
une contrainte unique insensible à la casse sur shop_id+name) ne sont pas
recréés, donc on peut relancer la commande avec un --count plus grand pour
compléter. Les clients créés par ce script ont leur adresse suffixée
" [SEED]", ce qui permet de les supprimer proprement avec --delete-seed sans
jamais toucher à un vrai client de la boutique (voir DuplicateClientNameError
dans customers_service.py : un vrai client portant déjà un nom candidat est
simplement sauté, jamais écrasé).
"""

import argparse
import random
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.main  # noqa: E402  (enregistre tous les modèles pour résoudre les relationships())
from app.db.session import SessionLocal  # noqa: E402
from app.modules.customers.customers_model import Client  # noqa: E402
from app.modules.identity.identity_model import Shop  # noqa: E402

FIRST_NAMES = [
    "Moussa", "Ousmane", "Ibrahima", "Mamadou", "Cheikh", "Abdoulaye", "Modou", "Alioune",
    "Babacar", "Serigne", "Amadou", "Pape", "Idrissa", "El Hadji", "Souleymane",
    "Aminata", "Fatou", "Awa", "Aïssatou", "Mariama", "Khady", "Ndeye", "Astou",
    "Coumba", "Bineta", "Rokhaya", "Marème", "Sokhna", "Absa", "Diarra",
]
LAST_NAMES = [
    "Diop", "Ndiaye", "Fall", "Gueye", "Sarr", "Diallo", "Ba", "Sow", "Diagne",
    "Faye", "Mbaye", "Sy", "Cissé", "Kane", "Thiam", "Seck", "Diouf", "Ndao",
    "Camara", "Traoré", "Sène", "Wade", "Niang", "Toure", "Dieng",
]
NEIGHBORHOODS = [
    "Parcelles Assainies, Dakar", "Grand Yoff, Dakar", "Médina, Dakar", "Sicap Liberté, Dakar",
    "Yoff, Dakar", "Ouakam, Dakar", "Guédiawaye", "Pikine", "Rufisque", "Thiès",
    "Mbour", "Kaolack", "Ziguinchor", "Saint-Louis", "Touba", "Diourbel",
    "Point E, Dakar", "Fann, Dakar", "HLM, Dakar", "Colobane, Dakar",
]
PHONE_PREFIXES = ["77", "78", "70", "76", "75"]
SEED_ADDRESS_SUFFIX = " [SEED]"


def sort_key(name: str) -> str:
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()


def build_candidate_names(target_count: int) -> list[str]:
    """Génère des combinaisons prénom+nom uniques, mélangées de façon
    reproductible (dépend de random.seed appelé par l'appelant)."""
    combos = [f"{f} {l}" for f in FIRST_NAMES for l in LAST_NAMES]
    random.shuffle(combos)
    return combos[:target_count]


def build_phone(used_phones: set[str]) -> str:
    while True:
        phone = random.choice(PHONE_PREFIXES) + "".join(str(random.randint(0, 9)) for _ in range(7))
        if phone not in used_phones:
            used_phones.add(phone)
            return phone


def build_address() -> str:
    neighborhood = random.choice(NEIGHBORHOODS)
    lot = random.randint(1, 999)
    return f"{random.choice(['Villa', 'Lot', 'Cité'])} {lot}, {neighborhood}{SEED_ADDRESS_SUFFIX}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shop-id", type=int, required=True, help="ID de la boutique à seeder")
    parser.add_argument("--count", type=int, default=130, help="Nombre total de clients de test visé (défaut: 130)")
    parser.add_argument("--dry-run", action="store_true", help="N'insère rien, affiche seulement ce qui serait fait")
    parser.add_argument("--delete-seed", action="store_true", help="Supprime les clients créés par ce script (adresse suffixée [SEED]) pour cette boutique")
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
                db.query(Client)
                .filter(Client.shop_id == args.shop_id, Client.address.like(f"%{SEED_ADDRESS_SUFFIX}"))
                .all()
            )
            print(f"{len(to_delete)} client(s) de seed à supprimer pour '{shop.name}' (id={shop.id}).")
            if not args.dry_run:
                for c in to_delete:
                    db.delete(c)
                db.commit()
                print("Supprimé.")
            return

        existing_names_lower = {
            n.lower() for (n,) in db.query(Client.name).filter(Client.shop_id == args.shop_id).all()
        }
        existing_phones = {
            p for (p,) in db.query(Client.phone).filter(Client.shop_id == args.shop_id, Client.phone.isnot(None)).all()
        }

        max_possible = len(FIRST_NAMES) * len(LAST_NAMES)
        candidates = build_candidate_names(min(args.count * 2, max_possible))
        to_create = [n for n in candidates if n.lower() not in existing_names_lower][: args.count]

        if not to_create:
            print(
                f"'{shop.name}' (id={shop.id}) a déjà {len(existing_names_lower)} client(s) "
                f">= la cible de {args.count}, ou le pool de noms est épuisé. Rien à faire."
            )
            return

        print(f"Boutique : {shop.name} (id={shop.id})")
        print(f"Clients existants : {len(existing_names_lower)}")
        print(f"Clients à créer   : {len(to_create)}")

        if args.dry_run:
            print("\n--dry-run : aperçu des 10 premiers et 10 derniers noms (tri alphabétique) :")
            preview = sorted(to_create, key=sort_key)
            for n in preview[:10]:
                print(f"  A→ {n}")
            for n in preview[-10:]:
                print(f"  Z→ {n}")
            return

        for name in to_create:
            phone = build_phone(existing_phones)
            db.add(Client(
                shop_id=args.shop_id,
                name=name,
                phone=phone,
                address=build_address(),
            ))

        db.commit()
        total_now = db.query(Client).filter(Client.shop_id == args.shop_id).count()
        print(f"\n{len(to_create)} client(s) créé(s). Total désormais pour la boutique : {total_now}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
