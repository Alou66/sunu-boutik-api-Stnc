"""Lecture seule: détection de l'état PostgreSQL de Sunu-Boutik.

Ne modifie jamais la base. Ne fait pas de create_all/upgrade/stamp.

Isolation de la configuration
-----------------------------
Ce module n'importe PAS `app.core.config.settings` : `Settings()` lit le
fichier `.env` du répertoire courant et exige `SECRET_KEY`, ce qui rendait le
résultat dépendant du poste de développement (et pouvait faire contacter la
base désignée par le `.env` local). L'URL de connexion vient uniquement de
l'argument `database_url` ou de la variable d'environnement `DATABASE_URL`.

Contrat de résultat
-------------------
`DetectionResult.to_dict()` renvoie toujours les mêmes clés (`RESULT_KEYS`) :
- `status` = "ok" : `state` vaut l'un des états métier de `STATES` ;
- `status` = "error" : `state` vaut None (état indéterminable) et `error`
  contient `{"code", "message"}`. Une base injoignable ou une configuration
  absente n'est jamais présentée comme `INCONSISTENT_DATABASE`.
- Une lecture indispensable en échec (tables, ENUM, `alembic_version`) donne
  le code `database_read_failed` (étape dans `details["step"]`) : elle n'est
  jamais assimilée à une absence d'objet ni à une base vierge.

Les messages d'exception ne sont jamais recopiés dans le résultat (ils
peuvent contenir l'URL de connexion ou l'hôte) : seul le type est exposé.
"""
from __future__ import annotations

import importlib
import os
import re
import sys
import types
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool


STATES = (
    "FRESH_DATABASE",
    "CREATE_ALL_INITIALIZED",
    "ALEMBIC_MANAGED",
    "INCONSISTENT_DATABASE",
)

STATUS_OK = "ok"
STATUS_ERROR = "error"

# Codes d'erreur (status="error", state=None)
ERROR_DATABASE_URL_MISSING = "database_url_missing"
ERROR_DATABASE_URL_INVALID = "database_url_invalid"
ERROR_DATABASE_UNREACHABLE = "database_unreachable"
ERROR_READ_ONLY_NOT_ENFORCED = "read_only_not_enforced"
ERROR_MODEL_METADATA_UNAVAILABLE = "model_metadata_unavailable"
ERROR_DATABASE_READ_FAILED = "database_read_failed"
ERROR_DETECTION_FAILED = "detection_failed"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VERSIONS_DIR = PROJECT_ROOT / "alembic" / "versions"

CONNECT_TIMEOUT_SECONDS = 10

# Même liste que alembic/env.py : chaque import enregistre ses tables (et ses
# ENUM) sur Base.metadata. Il n'existe pas de module central `app.models`.
MODEL_MODULES = (
    "app.modules.identity.identity_model",
    "app.modules.categories.categories_model",
    "app.modules.products.products_model",
    "app.modules.customers.customers_model",
    "app.modules.billing.billing_model",
    "app.modules.payments.payments_model",
    "app.modules.transformations.transformations_model",
    "app.modules.bon_client.bon_client_model",
    "app.modules.suppliers.suppliers_model",
    "app.modules.stock_receipts.stock_receipts_model",
    "app.modules.stock_initializations.stock_initializations_model",
    "app.modules.stock_adjustments.stock_adjustments_model",
)

_SESSION_MODULE = "app.db.session"


@dataclass
class DetectionResult:
    state: str | None
    declared_alembic_revision: str | None
    project_head_revision: str | None
    tables_found: list[str]
    unexpected_objects: list[dict[str, Any]]
    checks_passed: list[str]
    checks_failed: list[str]
    checks_not_verifiable: list[str]
    reasons: list[str]
    details: dict[str, Any] = field(default_factory=dict)
    read_only_enforced: bool = False
    status: str = STATUS_OK
    error: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # `status` et `error` en tête pour la lisibilité; jeu de clés inchangé.
        return {"status": data.pop("status"), "error": data.pop("error"), **data}


RESULT_KEYS = tuple(DetectionResult.__dataclass_fields__.keys())


class ModelMetadataError(Exception):
    """Échec d'import d'un module de modèles (erreur propagée, non masquée)."""

    def __init__(self, module: str, original: BaseException):
        super().__init__(f"Import impossible: {module} ({type(original).__name__})")
        self.module = module
        self.original = original


class DatabaseReadError(Exception):
    """Échec d'une lecture indispensable à la classification.

    Ne transporte que l'étape et le type d'exception : le message du pilote
    (qui peut contenir l'hôte, l'utilisateur ou l'URL) n'est jamais conservé.
    """

    def __init__(self, step: str, original: BaseException):
        super().__init__(f"Lecture impossible: {step} ({type(original).__name__})")
        self.step = step
        self.exception_type = type(original).__name__


# Étapes de lecture (DatabaseReadError.step)
READ_STEP_TABLES = "inspect_tables"
READ_STEP_ENUMS = "read_enums"
READ_STEP_ALEMBIC_VERSION = "read_alembic_version"


def error_result(
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    checks_passed: list[str] | None = None,
    checks_failed: list[str] | None = None,
    project_head_revision: str | None = None,
    read_only_enforced: bool = False,
) -> DetectionResult:
    """Résultat 'état indéterminable' : mêmes clés, `state` à None."""
    return DetectionResult(
        state=None,
        declared_alembic_revision=None,
        project_head_revision=project_head_revision,
        tables_found=[],
        unexpected_objects=[],
        checks_passed=list(checks_passed or []),
        checks_failed=list(checks_failed or [code]),
        checks_not_verifiable=["all"],
        reasons=[message],
        details=dict(details or {}),
        read_only_enforced=read_only_enforced,
        status=STATUS_ERROR,
        error={"code": code, "message": message},
    )


# --------------------------------------------------------------------------
# Métadonnées SQLAlchemy attendues
# --------------------------------------------------------------------------

def load_model_metadata() -> MetaData:
    """Charge les modèles de l'application et renvoie leur MetaData.

    - Si `app.db.session` est déjà chargé (appel depuis l'application ou les
      tests), on utilise le `Base` réel et on importe les modèles normalement.
    - Sinon (CLI), les modules de modèles sont importés contre un module
      `app.db.session` de substitution qui ne fournit qu'un `Base` neuf :
      `app.core.config` n'est pas importé, le `.env` n'est pas lu, aucun
      moteur n'est créé. Les modules importés ainsi sont ensuite retirés de
      `sys.modules` pour ne jamais être réutilisés par l'application.

    Aucune connexion PostgreSQL n'est ouverte. Une erreur d'import est levée
    sous forme de `ModelMetadataError` (jamais ignorée).
    """
    session_mod = sys.modules.get(_SESSION_MODULE)
    if session_mod is not None:
        _import_model_modules()
        return session_mod.Base.metadata
    return _load_model_metadata_isolated()


def _import_model_modules() -> None:
    for name in MODEL_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - reconverti, pas masqué
            raise ModelMetadataError(name, exc) from exc


def _load_model_metadata_isolated() -> MetaData:
    # Le paquet parent `app.db` (vide) est déjà chargé : ce module en fait partie.
    before = set(sys.modules)
    stub = types.ModuleType(_SESSION_MODULE)
    stub.__doc__ = "Substitut de app.db.session pour le détecteur (Base seul)."
    stub.Base = declarative_base()
    sys.modules[_SESSION_MODULE] = stub
    try:
        _import_model_modules()
        return stub.Base.metadata
    finally:
        added = [n for n in set(sys.modules) - before if n == "app" or n.startswith("app.")]
        added.append(_SESSION_MODULE)
        for name in added:
            mod = sys.modules.pop(name, None)
            parent_name, _, child = name.rpartition(".")
            parent = sys.modules.get(parent_name)
            if parent is not None and mod is not None and getattr(parent, child, None) is mod:
                delattr(parent, child)


def _expected_tables(metadata: MetaData) -> set[str]:
    return {
        tname
        for tname, table in metadata.tables.items()
        if not table.schema or table.schema == "public"
    }


def _expected_enums(metadata: MetaData) -> set[str]:
    from sqlalchemy import Enum as SAEnum  # ENUM postgresql en hérite

    enums: set[str] = set()
    for table in metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, SAEnum) and getattr(col.type, "name", None):
                enums.add(col.type.name)
    return enums


# --------------------------------------------------------------------------
# Historique Alembic du projet
# --------------------------------------------------------------------------

def _get_project_head_and_revisions() -> tuple[str | None, set[str]]:
    if not VERSIONS_DIR.exists():
        return None, set()
    revs: dict[str, list[str]] = {}
    for fn in os.listdir(VERSIONS_DIR):
        if not fn.endswith(".py") or fn.startswith("__"):
            continue
        path = VERSIONS_DIR / fn
        try:
            content = path.read_text()
        except Exception:
            continue
        m_rev = re.search(r"^revision\s*[:=].*?['\"]([a-z0-9]+)['\"]", content, re.M)
        m_down = re.search(r"^down_revision\s*[:=]\s*(.+?)(?:\n\n|\n[A-Za-z]|\Z)", content, re.M | re.S)
        if not m_rev:
            continue
        rev = m_rev.group(1)
        down = m_down.group(1).strip() if m_down else None
        downs = re.findall(r"['\"]([a-z0-9]+)['\"]", down) if down else []
        if not downs and down and re.match(r"^[a-z0-9]+$", down.strip().strip('",\'')):
            downs = [down.strip().strip('",\'')]
        if downs == [] and down and "None" in down:
            downs = []
        revs[rev] = downs
    all_downs: set[str] = set()
    for _, downs in revs.items():
        for d in downs:
            all_downs.add(d)
    heads = [r for r in revs if r not in all_downs]
    head = heads[0] if len(heads) == 1 else (heads[0] if heads else None)
    return head, set(revs.keys())


# --------------------------------------------------------------------------
# Lectures en base (connexion déjà en lecture seule)
# --------------------------------------------------------------------------

# Ces lectures ne renvoient jamais un résultat vide « par défaut » : une
# erreur est levée sous forme de DatabaseReadError, afin qu'une lecture
# impossible ne soit jamais confondue avec une absence d'objet.

def _get_declared_alembic_revision(conn) -> str | None:
    """Révision déclarée, ou None si la table (existante) est vide, contient
    plusieurs lignes ou une valeur NULL. Lève DatabaseReadError si la lecture
    elle-même échoue."""
    try:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    except Exception as exc:  # noqa: BLE001 - reconverti, pas masqué
        raise DatabaseReadError(READ_STEP_ALEMBIC_VERSION, exc) from exc
    if len(rows) != 1:
        return None
    v = rows[0][0]
    return str(v) if v is not None else None


def _get_tables(conn) -> list[str]:
    try:
        return sorted(inspect(conn).get_table_names(schema="public"))
    except Exception as exc:  # noqa: BLE001 - reconverti, pas masqué
        raise DatabaseReadError(READ_STEP_TABLES, exc) from exc


def _get_enums(conn) -> list[str]:
    """Liste (éventuellement vide) des ENUM ; lève DatabaseReadError si la
    lecture échoue."""
    try:
        res = conn.execute(text("SELECT typname FROM pg_type WHERE typtype='e' ORDER BY typname"))
        return [r[0] for r in res.fetchall()]
    except Exception as exc:  # noqa: BLE001 - reconverti, pas masqué
        raise DatabaseReadError(READ_STEP_ENUMS, exc) from exc


# --------------------------------------------------------------------------
# Détection
# --------------------------------------------------------------------------

def detect_state(database_url: str | None = None) -> DetectionResult:
    """Détecte l'état de la base. Ne lève pas : toute erreur devient un
    résultat `status="error"` avec `state=None`."""
    try:
        return _detect_state(database_url)
    except Exception as exc:  # noqa: BLE001 - garde-fou du contrat
        return error_result(
            ERROR_DETECTION_FAILED,
            "Échec inattendu de la détection",
            details={"exception_type": type(exc).__name__},
        )


def _detect_state(database_url: str | None) -> DetectionResult:
    url = (database_url or os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        return error_result(
            ERROR_DATABASE_URL_MISSING,
            "DATABASE_URL manquant ou non configuré",
        )

    try:
        parsed_url = make_url(url)
    except Exception as exc:  # noqa: BLE001 - le message contiendrait l'URL
        return error_result(
            ERROR_DATABASE_URL_INVALID,
            "DATABASE_URL invalide",
            details={"exception_type": type(exc).__name__},
        )

    # Métadonnées chargées avant toute connexion : un échec d'import ne doit
    # pas provoquer d'accès réseau inutile.
    try:
        metadata = load_model_metadata()
    except ModelMetadataError as exc:
        return error_result(
            ERROR_MODEL_METADATA_UNAVAILABLE,
            "Chargement des modèles SQLAlchemy impossible",
            details={"module": exc.module, "exception_type": type(exc.original).__name__},
        )
    expected_tables = _expected_tables(metadata)
    expected_enums = _expected_enums(metadata)
    project_head, known_revisions = _get_project_head_and_revisions()

    checks_passed: list[str] = ["model_metadata_loaded"]
    checks_failed: list[str] = []
    checks_not_verifiable: list[str] = []
    reasons: list[str] = []
    unexpected_objects: list[dict[str, Any]] = []

    connect_args: dict[str, Any] = {}
    if parsed_url.get_driver_name() == "psycopg2":
        connect_args["connect_timeout"] = CONNECT_TIMEOUT_SECONDS
    try:
        engine = create_engine(parsed_url, poolclass=NullPool, connect_args=connect_args)
    except Exception as exc:  # noqa: BLE001 - pilote absent, URL non supportée...
        return error_result(
            ERROR_DATABASE_URL_INVALID,
            "DATABASE_URL non utilisable (dialecte ou pilote indisponible)",
            details={"exception_type": type(exc).__name__},
            project_head_revision=project_head,
        )

    try:
        try:
            conn = engine.connect()
        except DBAPIError as exc:
            return error_result(
                ERROR_DATABASE_UNREACHABLE,
                "Connexion PostgreSQL impossible",
                details={"exception_type": type(exc.orig).__name__ if exc.orig else type(exc).__name__},
                checks_passed=checks_passed,
                project_head_revision=project_head,
            )
        with conn:
            try:
                conn.execute(text("BEGIN READ ONLY"))
                ro = conn.execute(text("SHOW transaction_read_only")).scalar()
            except Exception as exc:  # noqa: BLE001
                return error_result(
                    ERROR_READ_ONLY_NOT_ENFORCED,
                    "Impossible d'activer une transaction en lecture seule",
                    details={"exception_type": type(exc).__name__},
                    checks_passed=checks_passed,
                    project_head_revision=project_head,
                )
            if str(ro).lower() != "on":
                return error_result(
                    ERROR_READ_ONLY_NOT_ENFORCED,
                    "Transaction en lecture seule non confirmée par le serveur",
                    checks_passed=checks_passed,
                    project_head_revision=project_head,
                )
            checks_passed.append("begin_read_only")

            # Toute lecture en échec rend l'état indéterminable : aucune
            # classification n'est produite à partir de données partielles.
            # alembic_version n'est interrogée que si la table existe (sinon
            # la requête échouerait par construction, sans être une erreur).
            try:
                tables_found = _get_tables(conn)
                checks_passed.append(READ_STEP_TABLES)
                enums_found = _get_enums(conn)
                checks_passed.append(READ_STEP_ENUMS)
                declared_rev = None
                if "alembic_version" in tables_found:
                    declared_rev = _get_declared_alembic_revision(conn)
                    checks_passed.append(READ_STEP_ALEMBIC_VERSION)
            except DatabaseReadError as exc:
                return error_result(
                    ERROR_DATABASE_READ_FAILED,
                    "Lecture de la base impossible - état indéterminable",
                    details={"step": exc.step, "exception_type": exc.exception_type},
                    checks_passed=checks_passed,
                    checks_failed=[ERROR_DATABASE_READ_FAILED, exc.step],
                    project_head_revision=project_head,
                    read_only_enforced=True,
                )
    finally:
        engine.dispose()

    user_tables = [t for t in tables_found if t != "alembic_version"]
    has_alembic_version = "alembic_version" in tables_found

    if len(user_tables) == 0 and not has_alembic_version:
        checks_passed.append("empty_public_schema")
        return DetectionResult(
            state="FRESH_DATABASE",
            declared_alembic_revision=None,
            project_head_revision=project_head,
            tables_found=tables_found,
            unexpected_objects=[],
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            checks_not_verifiable=checks_not_verifiable,
            reasons=["Schéma public vide sans alembic_version - base vierge"],
            details={"expected_tables_count": len(expected_tables), "enums_found": enums_found},
            read_only_enforced=True,
        )

    if has_alembic_version and len(user_tables) == 0:
        checks_failed.append("alembic_version_alone")
        reasons.append("Table alembic_version isolée sans tables applicatives - état ambigu, non considéré vierge")
        return DetectionResult(
            state="INCONSISTENT_DATABASE",
            declared_alembic_revision=declared_rev,
            project_head_revision=project_head,
            tables_found=tables_found,
            unexpected_objects=[{"type": "table", "name": "alembic_version", "note": "isolated"}],
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            checks_not_verifiable=checks_not_verifiable,
            reasons=reasons,
            details={"enums_found": enums_found},
            read_only_enforced=True,
        )

    unexpected = []
    for t in user_tables:
        if t not in expected_tables:
            unexpected.append({"type": "table", "name": t})
    if unexpected:
        unexpected_objects.extend(unexpected)
        checks_failed.append("unexpected_tables")
        reasons.append("Tables inattendues détectées")

    if has_alembic_version:
        if declared_rev is None:
            checks_failed.append("alembic_version_invalid")
            reasons.append("alembic_version présente mais révision non lisible ou ambiguë")
            return DetectionResult(
                state="INCONSISTENT_DATABASE",
                declared_alembic_revision=declared_rev,
                project_head_revision=project_head,
                tables_found=tables_found,
                unexpected_objects=unexpected_objects,
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                checks_not_verifiable=checks_not_verifiable,
                reasons=reasons,
                details={"enums_found": enums_found},
                read_only_enforced=True,
            )
        if declared_rev not in known_revisions:
            checks_failed.append("alembic_revision_unknown")
            reasons.append("Révision déclarée inconnue dans l'historique du projet")
            return DetectionResult(
                state="INCONSISTENT_DATABASE",
                declared_alembic_revision=declared_rev,
                project_head_revision=project_head,
                tables_found=tables_found,
                unexpected_objects=unexpected_objects,
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                checks_not_verifiable=checks_not_verifiable,
                reasons=reasons,
                details={"enums_found": enums_found},
                read_only_enforced=True,
            )
        checks_not_verifiable.append("historical_schema_reconstruction_full")
        reasons.append("Vérification complète du schéma historique par révision impossible depuis les métadonnées actuelles; compatibilité avec la révision déclarée non démontrée de manière exhaustive")
        checks_failed.append("historical_compatibility_not_demonstrated")
        return DetectionResult(
            state="INCONSISTENT_DATABASE",
            declared_alembic_revision=declared_rev,
            project_head_revision=project_head,
            tables_found=tables_found,
            unexpected_objects=unexpected_objects,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            checks_not_verifiable=checks_not_verifiable,
            reasons=reasons,
            details={"enums_found": enums_found},
            read_only_enforced=True,
        )

    missing_tables = expected_tables - set(user_tables)
    missing_enums = expected_enums - set(enums_found)
    if missing_tables:
        checks_failed.append("missing_expected_tables")
        reasons.append("Tables attendues manquantes")
    if missing_enums:
        checks_failed.append("missing_expected_enums")
        reasons.append("Types ENUM attendus manquants")

    if unexpected_objects or missing_tables or missing_enums:
        reasons.append("Correspondance exhaustive avec les métadonnées SQLAlchemy actuelles non démontrée ou incomplète")
        return DetectionResult(
            state="INCONSISTENT_DATABASE",
            declared_alembic_revision=None,
            project_head_revision=project_head,
            tables_found=tables_found,
            unexpected_objects=unexpected_objects,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            checks_not_verifiable=checks_not_verifiable,
            reasons=reasons,
            details={"expected_tables_count": len(expected_tables), "enums_found": enums_found},
            read_only_enforced=True,
        )

    checks_passed.append("expected_tables_and_enums_present")
    checks_not_verifiable.append("full_column_constraint_index_comparison")
    checks_failed.append("exhaustive_schema_comparison_not_completed")
    reasons.append("Comparaison exhaustive (colonnes/types/nullabilité/PK/FK/UNIQUE/CHECK/index/ENUM) non complètement implémentée; correspondance non démontrée de manière exhaustive")
    return DetectionResult(
        state="INCONSISTENT_DATABASE",
        declared_alembic_revision=None,
        project_head_revision=project_head,
        tables_found=tables_found,
        unexpected_objects=unexpected_objects,
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        checks_not_verifiable=checks_not_verifiable,
        reasons=reasons,
        details={"expected_tables_count": len(expected_tables), "enums_found": enums_found},
        read_only_enforced=True,
    )
