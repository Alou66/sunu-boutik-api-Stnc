"""Garde-fou de non-régression pour la migration : le schéma OpenAPI généré
par l'application doit rester identique à `openapi_reference.json`, figé
avant tout déplacement de code (voir le playbook de migration, étape "avant").

Un module migré (routes, chemins, schémas Pydantic identiques) ne doit
JAMAIS faire échouer ce test. S'il échoue, soit une route a changé de forme
par accident (à corriger), soit un changement de contrat est réellement
voulu — auquel cas ce fichier de référence se régénère volontairement,
dans un commit séparé et nommé comme tel, jamais au passage d'une migration.
"""
import json
from pathlib import Path

REFERENCE_PATH = Path(__file__).parent / "openapi_reference.json"


def test_openapi_schema_matches_frozen_reference(client):
    current = client.get("/openapi.json").json()
    reference = json.loads(REFERENCE_PATH.read_text())
    assert current == reference, (
        "Le schéma OpenAPI a changé par rapport à la référence figée. "
        "Si ce changement est un effet de bord non voulu d'un déplacement de code, "
        "corrigez le code. S'il est volontaire, régénérez openapi_reference.json "
        "dans un commit séparé, explicitement nommé."
    )
