# syntax=docker/dockerfile:1

# ---- Stage 1 : build des dépendances ----------------------------------
# gcc/libpq-dev ne sont nécessaires que pour compiler certaines libs Python
# (psycopg2-binary, bcrypt, reportlab). On les isole dans cette image pour ne
# pas les retrouver dans l'image finale.
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---- Stage 2 : image d'exécution ---------------------------------------
FROM python:3.12-slim AS runtime

WORKDIR /app

# libpq5 : lib client Postgres nécessaire à l'exécution (psycopg2)
# curl : utilisé par le HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system app && adduser --system --ingroup app --home /app app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY . .

RUN mkdir -p /app/uploads \
    && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Pas d'étape "alembic upgrade head" automatique ici : sur une base neuve,
# Base.metadata.create_all() (déclenché au startup de l'app, voir
# app/main.py::on_startup) crée déjà le schéma complet à jour. Les
# migrations Alembic ne servent qu'à faire évoluer une base existante
# (ex. la base de prod) — voir le README de sunu-boutik-infra pour les
# lancer manuellement au besoin : `docker compose exec api alembic upgrade head`.
#
# Un seul worker ici (contrairement au déploiement Render qui en utilise 2) :
# app/main.py exécute Base.metadata.create_all() + la création des types
# ENUM Postgres à CHAQUE démarrage de worker Uvicorn ; avec plusieurs workers
# démarrant en parallèle sur une base vide, deux processus peuvent tenter de
# créer le même type ENUM simultanément et l'un des deux crashe
# (UniqueViolation sur pg_type). Un conteneur = un process est de toute façon
# l'usage recommandé avec Docker (on scale en ajoutant des réplicas du
# service plutôt qu'en augmentant --workers).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
