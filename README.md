# Sunu Boutik — API

API backend de **Sunu Boutik**, une application de gestion de boutique (stock, ventes, facturation, caisse, clients, fournisseurs) pensée pour plusieurs commerces indépendants (multi-boutique / multi-tenant).

Ce dépôt contient uniquement le **backend** (FastAPI + PostgreSQL). Le frontend correspondant est le projet voisin [`sunu-boutik-web`](../sunu-boutik-web) (Next.js) — sa logique est résumée en fin de document pour comprendre comment les deux communiquent.

---

## 1. Le concept métier

Sunu Boutik permet à des commerçants de gérer leur boutique au quotidien : articles, stock, ventes, clients, fournisseurs, réceptions de marchandises et statistiques. L'application est **multi-tenant** : chaque boutique (`Shop`) est isolée des autres, mais toutes partagent la même API et la même base de données.

### Cycle de vie d'une boutique

1. Un commerçant s'inscrit (`POST /auth/register`) : cela crée une `Shop` au statut `pending` et un `User` avec le rôle `owner`.
2. Un **administrateur de la plateforme** (rôle `admin`, distinct des boutiques) examine la demande dans le back-office admin et l'**approuve** ou la **rejette** (`ShopStatus`: `pending` → `approved` / `rejected`).
3. Tant que la boutique n'est pas `approved`, ses utilisateurs ne peuvent pas se connecter normalement (voir `ShopPendingError` / `ShopRejectedError` dans `identity_service.py`).
4. Une fois approuvée, le propriétaire (`owner`) peut inviter des employés (`employee`) qui héritent des mêmes données de boutique (`shop_id`) mais avec des permissions réduites.

### Rôles utilisateurs (`UserRole`)

| Rôle | Portée | Usage |
|---|---|---|
| `admin` | Plateforme (aucune boutique) | Valide/rejette les inscriptions, supervise toutes les boutiques |
| `owner` | Une boutique | Accès complet à sa boutique (gestion, stats, employés) |
| `employee` | Une boutique | Opérations du quotidien (caisse, ventes) avec droits restreints |

Toutes les données métier (produits, clients, factures, fournisseurs, etc.) sont rattachées à une `shop_id` : c'est la clé qui garantit l'isolation entre boutiques.

---

## 2. Modules fonctionnels

Le code est organisé en **modules verticaux** (`app/modules/<domaine>/`), chacun suivant la même structure interne : `*_model.py` (tables SQLAlchemy), `*_dto.py` (schémas Pydantic entrée/sortie), `*_repository.py` (accès BDD), `*_service.py` (logique métier), `*_mapper.py` (modèle → DTO), `*_route.py` (endpoints FastAPI).

| Module | Rôle |
|---|---|
| `identity` | Authentification (JWT), inscription boutique, mot de passe oublié, profil courant (`/auth/*`) |
| `admin` | Back-office plateforme : validation/rejet des boutiques (`/admin/*`) |
| `categories` | Catégories d'articles (`/categories`) |
| `products` | Catalogue d'articles, stock, prix d'achat/vente, **transformation d'unité** (ex : 1 carton = 4 seaux) (`/products`) |
| `customers` | Fiches clients de la boutique (`/clients`) |
| `billing` | Facturation : création de factures, lignes, génération de PDF (`/invoices`) |
| `payments` | Encaissements sur factures, calcul du statut payé/partiel/impayé (`/invoices/{id}/payments`) |
| `cashier` | Vue "caisse" : suivi des ventes/encaissements du jour (`/caisse`) |
| `transformations` | Historique des transformations de stock entre forme principale et secondaire (`/transformations`) |
| `bon_client` | Bons/avoirs clients (crédits accordés à un client) (`/bons-clients`) |
| `suppliers` | Fournisseurs de la boutique (`/suppliers`) |
| `stock_receipts` | Réceptions de marchandises / approvisionnements, mise à jour du stock (`/stock-receipts`) |
| `statistics` | Indicateurs agrégés (ventes, marges, top produits, etc.) (`/statistics`) |

### Points métier notables

- **Articles transformables** (`Product.is_transformable`) : un article peut exister sous deux formes liées par un taux de conversion (`conversion_ratio`), par exemple un carton vendable aussi à l'unité. Une contrainte SQL (`CheckConstraint`) garantit la cohérence des champs de conversion en plus de la validation applicative.
- **Statut de facture dérivé** (`Invoice.status`) : jamais stocké tel quel, toujours recalculé depuis `amount_paid` vs `total` (`unpaid` / `partial` / `paid`), pour éviter toute divergence.
- **Verrouillage de la numérotation des factures** : un verrou `FOR UPDATE` sur la boutique évite les doublons de numéro de facture en cas d'accès concurrents, doublé d'une contrainte `UNIQUE(shop_id, number)`.
- **Coût figé à la vente** (`InvoiceLine.cost_price`) : le prix d'achat est capturé au moment de la vente pour calculer une marge réelle même si le prix d'achat du produit change ensuite.

---

## 3. Stack technique

| Domaine | Choix |
|---|---|
| Framework API | [FastAPI](https://fastapi.tiangolo.com/) 0.115 |
| Serveur ASGI | Uvicorn |
| Base de données | PostgreSQL (hébergée sur [Neon](https://neon.tech) en développement/production) |
| ORM / migrations | SQLAlchemy 2.0 + Alembic |
| Authentification | JWT (`python-jose`) + hachage `bcrypt` via `passlib` |
| Rate limiting | `slowapi` (ex : 5 tentatives/min sur l'inscription, 10/min sur le login) |
| Emails transactionnels | SMTP Gmail (notifications d'inscription) |
| Génération de PDF | `reportlab` (factures) |
| Export Excel | `openpyxl` |
| Tests | `pytest` (tests dits "characterization" par module) |
| Déploiement | Docker + [Render](https://render.com) (`render.yaml`) |

---

## 4. Structure du projet

```
sunu-boutik-api/
├── app/
│   ├── main.py               # Point d'entrée FastAPI, middlewares, montage des routers
│   ├── core/
│   │   ├── config.py         # Settings (variables d'environnement, pydantic-settings)
│   │   ├── security.py       # Hash mot de passe, création/décodage JWT
│   │   ├── deps.py           # Dépendances FastAPI : get_current_user, get_current_admin
│   │   ├── email.py          # Envoi d'emails transactionnels (SMTP Gmail)
│   │   ├── limiter.py        # Configuration slowapi (rate limiting)
│   │   └── uploads.py        # Gestion des fichiers uploadés (logos, etc.)
│   ├── db/
│   │   └── session.py        # Engine SQLAlchemy, Base, SessionLocal, get_db
│   └── modules/               # Un dossier par domaine métier (voir tableau ci-dessus)
├── alembic/                   # Migrations de base de données
├── tests/
│   └── characterization/      # Tests de non-régression par module + contrat OpenAPI
├── scripts/                   # Scripts utilitaires (seed de données de démo)
├── uploads/                   # Fichiers uploadés en local (logos boutiques, etc.)
├── requirements.txt
├── Dockerfile
├── render.yaml                 # Déploiement sur Render
└── .env.example
```

---

## 5. Authentification & sécurité

- **JWT Bearer** : après login (`POST /auth/login`), le client reçoit un `access_token` à renvoyer dans l'en-tête `Authorization: Bearer <token>`.
- `get_current_user` (dans `app/core/deps.py`) décode le token, retrouve l'utilisateur en base et vérifie qu'il est actif.
- `get_current_admin` restreint certaines routes au rôle `admin` (back-office plateforme).
- **En-têtes de sécurité** ajoutés à chaque réponse : `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`.
- **CORS** piloté par la variable `CORS_ORIGINS` (liste d'origines séparées par des virgules).
- **Rate limiting** sur les routes sensibles (inscription, login, mot de passe oublié) pour limiter le bruteforce.
- Un compte **admin est auto-créé au démarrage** de l'application si `ADMIN_EMAIL`/`ADMIN_PASSWORD` sont définis et qu'aucun compte avec cet email n'existe déjà (`_seed_admin` dans `main.py`).

---

## 6. Configuration (variables d'environnement)

Copier `.env.example` vers `.env` et renseigner :

| Variable | Description |
|---|---|
| `DATABASE_URL` | URL de connexion PostgreSQL |
| `SECRET_KEY` | Clé secrète de signature des JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Durée de validité du token (défaut : 1440 = 24h) |
| `CORS_ORIGINS` | Origines autorisées, séparées par des virgules |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_SENDER_NAME` | Config email transactionnel (notifications d'inscription) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Compte admin plateforme auto-créé au démarrage |
| `FRONTEND_URL` | URL du frontend (utilisée dans les liens des emails) |

⚠️ Le fichier `.env` présent dans le dossier contient des identifiants réels (base Neon) : ne jamais le committer ni le partager. Il est déjà listé dans `.gitignore`.

---

## 7. Lancer le projet en local

```bash
# 1. Créer et activer un environnement virtuel
python3 -m venv .venv
source .venv/bin/activate

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Configurer l'environnement
cp .env.example .env
# éditer .env avec vos propres valeurs

# 4. Appliquer les migrations
alembic upgrade head

# 5. Lancer le serveur de développement
uvicorn app.main:app --reload
```

L'API est alors disponible sur `http://localhost:8000`, avec la documentation interactive auto-générée :

- Swagger UI : `http://localhost:8000/docs`
- ReDoc : `http://localhost:8000/redoc`
- Health check : `http://localhost:8000/health`

### Lancer les tests

```bash
pytest
```

Les tests sont organisés par module dans `tests/characterization/`, plus un test de contrat OpenAPI (`test_openapi_contract.py`) qui garantit que le schéma exposé par l'API ne change pas de façon inattendue.

### Jeux de données de démo

```bash
python scripts/seed_products.py
python scripts/seed_customers.py
```

---

## 8. Déploiement

- **Docker** : `Dockerfile` fournit une image basée sur `python:3.12-slim`, installe les dépendances système nécessaires à `psycopg2` et `reportlab`, puis lance `uvicorn` avec 2 workers.
- **Render** : `render.yaml` décrit un service web Python déployé automatiquement (build + start command, health check sur `/health`, variables d'environnement à renseigner dans le dashboard Render).

---

## 9. Le frontend — `sunu-boutik-web`

Le frontend est un projet **Next.js 16 (App Router)** en TypeScript, séparé de ce dépôt mais conçu pour consommer cette API.

### Stack

- **Next.js 16** + **React 19**, rendu App Router
- **TypeScript**
- **Tailwind CSS v4**

### Organisation

```
sunu-boutik-web/
├── app/                # Routes Next.js (App Router)
│   ├── login/, register/, forgot-password/, change-password/
│   ├── admin/          # Espace back-office plateforme (login, clients, demandes)
│   └── dashboard/      # Espace boutique connectée
│       ├── articles/, categories/, clients/, fournisseurs/
│       ├── factures/, bons-clients/, caisse/
│       ├── approvisionnements/, transformations/
│       ├── statistiques/, profil/
├── features/           # Logique métier par domaine (miroir des modules backend)
│   ├── auth/, products/, categories/, clients/, suppliers/
│   ├── factures/, bon-client/, caisse/, approvisionnements/
│   ├── transformations/, statistics/, profil/, admin/
├── components/         # Composants UI partagés
└── lib/
    ├── api.ts          # Client HTTP centralisé vers l'API FastAPI
    └── auth-context.tsx# Contexte React d'authentification (token, utilisateur courant)
```

Cette organisation en `features/` **reflète directement les modules du backend** (`products`, `categories`, `billing` → `factures`, `bon_client` → `bon-client`, `cashier` → `caisse`, `stock_receipts` → `approvisionnements`, etc.), ce qui facilite la navigation entre les deux dépôts : pour comprendre une fonctionnalité de bout en bout, on regarde `app/modules/<x>/` côté API et `features/<x>/` côté web.

### Comment le frontend parle à l'API

- `lib/api.ts` centralise tous les appels HTTP vers `NEXT_PUBLIC_API_URL` (par défaut `http://localhost:8000`).
- Le token JWT est stocké dans `localStorage` (clé `token` pour l'espace boutique, `admin_token` pour l'espace admin — deux sessions indépendantes possibles).
- Chaque requête ajoute automatiquement l'en-tête `Authorization: Bearer <token>`.
- Un **cache mémoire de courte durée (15s)** est appliqué aux requêtes `GET` pour accélérer la navigation, et est **invalidé automatiquement** dès qu'une mutation (`POST`/`PATCH`/`DELETE`) est effectuée.
- `auth-context.tsx` expose l'utilisateur courant et l'état de connexion à toute l'application via React Context.

### Les deux espaces de l'application web

1. **`/dashboard/*`** : espace boutique — utilisé au quotidien par les `owner` et `employee` d'une boutique approuvée (produits, ventes, caisse, clients, etc.).
2. **`/admin/*`** : espace plateforme — réservé au rôle `admin`, pour approuver/rejeter les demandes d'inscription de boutiques et superviser les clients de la plateforme.

### Lancer le frontend en local

```bash
cd ../sunu-boutik-web
npm install
npm run dev
```

Par défaut, il se connecte à l'API sur `http://localhost:8000` (variable `NEXT_PUBLIC_API_URL` à définir dans un `.env.local` si l'API tourne ailleurs).

---

## 10. Résumé du flux complet

```
Inscription boutique (web /register)
        │
        ▼
POST /auth/register  ──►  Shop(status=pending) + User(role=owner)
        │
        ▼
Email de notification (SMTP Gmail) à l'équipe + au commerçant
        │
        ▼
Admin plateforme (web /admin) ──► POST /admin/shops/{id}/approve | /reject
        │
        ▼
Boutique approuvée ──► login possible (POST /auth/login) ──► JWT
        │
        ▼
Espace boutique (web /dashboard) : produits, ventes/factures, caisse,
clients, fournisseurs, approvisionnements, statistiques
```
