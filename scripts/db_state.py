#!/usr/bin/env python3
"""CLI pour détecter l'état de la base PostgreSQL (lecture seule).

L'URL vient uniquement de la variable d'environnement DATABASE_URL : le
fichier `.env` n'est jamais lu, quel que soit le répertoire courant.

Codes retour :
  0  détection réussie (sans --strict : tout état autre qu'INCONSISTENT_DATABASE ;
     avec --strict : FRESH_DATABASE uniquement)
  1  base détectée comme INCONSISTENT_DATABASE (sans --strict)
  2  --strict : état détecté mais différent de FRESH_DATABASE
  3  état indéterminable (configuration absente, connexion impossible,
     erreur de détection), y compris avec --strict
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EXIT_OK = 0
EXIT_INCONSISTENT = 1
EXIT_STRICT_NOT_FRESH = 2
EXIT_UNDETERMINED = 3

SAFE_STATES = {"FRESH_DATABASE"}


def _fallback_error(exc: BaseException) -> dict:
    """Utilisé seulement si le détecteur lui-même n'est pas importable :
    reproduit le jeu de clés de DetectionResult.to_dict()."""
    message = "Échec du chargement du détecteur"
    return {
        "status": "error",
        "error": {"code": "detection_failed", "message": message},
        "state": None,
        "declared_alembic_revision": None,
        "project_head_revision": None,
        "tables_found": [],
        "unexpected_objects": [],
        "checks_passed": [],
        "checks_failed": ["detection_failed"],
        "checks_not_verifiable": ["all"],
        "reasons": [message],
        "details": {"exception_type": type(exc).__name__},
        "read_only_enforced": False,
    }


def exit_code(out: dict, strict: bool) -> int:
    if out.get("status") != "ok" or out.get("state") is None:
        return EXIT_UNDETERMINED
    if strict:
        return EXIT_OK if out["state"] in SAFE_STATES else EXIT_STRICT_NOT_FRESH
    return EXIT_INCONSISTENT if out["state"] == "INCONSISTENT_DATABASE" else EXIT_OK


def _print_text(out: dict) -> None:
    if out["status"] != "ok":
        err = out["error"] or {}
        print(f"État: indéterminable ({err.get('code')})", file=sys.stderr)
        print(f"Erreur: {err.get('message')}", file=sys.stderr)
        return
    print(f"État: {out['state']}")
    print(f"Révision Alembic déclarée: {out['declared_alembic_revision']}")
    print(f"HEAD projet: {out['project_head_revision']}")
    print(f"Tables trouvées: {len(out['tables_found'])}")
    print(f"Contrôles réussis: {len(out['checks_passed'])}")
    print(f"Contrôles échoués: {len(out['checks_failed'])}")
    print(f"Contrôles non vérifiables: {len(out['checks_not_verifiable'])}")
    if out["reasons"]:
        print("Raisons:")
        for r in out["reasons"]:
            print(f"  - {r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Détecteur d'état PostgreSQL (lecture seule)")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    parser.add_argument("--strict", action="store_true", help="Mode strict - échoue si état non sûr")
    args = parser.parse_args()

    try:
        from app.db.state_detector import detect_state
    except Exception as exc:  # noqa: BLE001 - le contrat JSON doit tenir
        out = _fallback_error(exc)
    else:
        # detect_state ne lève pas : les erreurs sont des résultats status="error".
        out = detect_state().to_dict()

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        _print_text(out)
    return exit_code(out, args.strict)


if __name__ == "__main__":
    sys.exit(main())
