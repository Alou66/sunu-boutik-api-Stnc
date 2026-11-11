"""Tests du détecteur d'état (lecture seule).

Les sous-processus sont lancés avec un environnement minimal (sans
DATABASE_URL, SECRET_KEY ni autre variable applicative) : le résultat ne doit
dépendre ni du `.env` du poste, ni du répertoire courant. Les tests qui ont
besoin d'une connexion démarrent un PostgreSQL Docker temporaire, publié sur
127.0.0.1 uniquement, et le suppriment en fin de test.
"""
import contextlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from app.db.state_detector import RESULT_KEYS

# Racine du projet calculée depuis l'emplacement de ce fichier (tests/ -> racine)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_STATE_SCRIPT = PROJECT_ROOT / "scripts" / "db_state.py"

UNREACHABLE_URL = "postgresql://nouser:nopass-secret@127.0.0.1:1/nodb"

# Variables système conservées ; toute variable applicative est exclue.
_SYSTEM_ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")


def _run(cmd, env=None, timeout=60, cwd=None):
    try:
        res = subprocess.run(cmd, shell=isinstance(cmd, str), env=env, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return res.returncode, res.stdout, res.stderr
    except subprocess.TimeoutExpired as e:
        return -1, e.stdout or b"", e.stderr or b""


def _clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if k in _SYSTEM_ENV_KEYS}
    env.update(extra)
    return env


def _run_cli(*args, env, cwd, timeout=60):
    return _run([sys.executable, str(DB_STATE_SCRIPT), *args], env=env, cwd=cwd, timeout=timeout)


def _docker_available():
    rc, _, _ = _run("docker version >/dev/null 2>&1", timeout=10)
    return rc == 0


@contextlib.contextmanager
def _temp_postgres(prefix, db):
    """PostgreSQL jetable (Docker), port dynamique sur 127.0.0.1 ; toujours supprimé."""
    with _temp_postgres_container(prefix, db) as (_, url):
        yield url


@contextlib.contextmanager
def _temp_postgres_container(prefix, db):
    """Comme `_temp_postgres`, mais fournit aussi le nom du conteneur jetable."""
    if not _docker_available():
        pytest.skip("Docker indisponible - test d'intégration ignoré")
    name = f"{prefix}-{uuid.uuid4().hex[:8]}"
    created = False
    try:
        rc, out, err = _run(f"docker run --name {name} -e POSTGRES_DB={db} -e POSTGRES_USER=u -e POSTGRES_PASSWORD=p -p 127.0.0.1::5432 -d postgres:16", timeout=120)
        if rc != 0:
            pytest.skip(f"Impossible de démarrer Postgres temporaire: {err[:200]}")
        created = True
        rc_p, out_p, _ = _run(f"docker port {name} 5432/tcp", timeout=10)
        if rc_p != 0:
            pytest.fail("Impossible d'obtenir le port dynamique")
        # format 127.0.0.1:xxxxx
        pm = re.search(r":(\d+)", out_p.decode())
        if not pm:
            pytest.fail("Format de port inattendu")
        port = pm.group(1)
        # -h 127.0.0.1 : pendant l'initialisation, le serveur temporaire de
        # l'image n'écoute que sur la socket Unix ; on attend le vrai serveur TCP.
        for _ in range(60):
            rc2, _, _ = _run(f"docker exec {name} pg_isready -h 127.0.0.1 -U u -d {db} >/dev/null 2>&1", timeout=5)
            if rc2 == 0:
                break
            time.sleep(1)
        else:
            pytest.fail("Postgres temporaire non prêt")
        yield name, f"postgresql://u:p@127.0.0.1:{port}/{db}"
    finally:
        if created:
            _run(f"docker stop {name} >/dev/null 2>&1", timeout=30)
            _run(f"docker rm {name} >/dev/null 2>&1", timeout=30)


def _parse(out):
    try:
        data = json.loads(out)
    except Exception as e:
        pytest.fail(f"JSON invalide: {e}")
    assert tuple(sorted(data)) == tuple(sorted(RESULT_KEYS)), "jeu de clés JSON instable"
    return data


def _assert_undetermined(data, code):
    assert data["status"] == "error"
    assert data["state"] is None
    assert data["error"]["code"] == code
    assert data["error"]["message"]
    assert data["read_only_enforced"] is False


def _expected_model_tables():
    # Base réelle, chargée par conftest via app.main (mécanisme normal de l'application)
    from app.db.session import Base
    return set(Base.metadata.tables)


# ---------------------------------------------------------------------------
# Intégration : PostgreSQL temporaire
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_fresh_database_autonomous(tmp_path):
    with _temp_postgres("sunu-dbstate-fresh", "dbfresh") as url:
        env = _clean_env(DATABASE_URL=url)
        for cwd in (tmp_path, PROJECT_ROOT):  # résultat indépendant du répertoire courant
            rc, out, err = _run_cli("--json", env=env, cwd=cwd)
            data = _parse(out)
            assert rc == 0, err
            assert data["status"] == "ok"
            assert data["error"] is None
            assert data["state"] == "FRESH_DATABASE"
            assert data["declared_alembic_revision"] is None
            assert data["read_only_enforced"] is True
            assert data["details"]["expected_tables_count"] == len(_expected_model_tables())
            assert "reasons" in data


@pytest.mark.integration
def test_strict_fresh_exit_code(tmp_path):
    with _temp_postgres("sunu-dbstate-fresh-s", "dbfresh2") as url:
        rc, out, err = _run_cli("--strict", env=_clean_env(DATABASE_URL=url), cwd=tmp_path)
        assert rc == 0, err


@pytest.mark.integration
def test_create_all_database_uses_model_metadata(tmp_path):
    """Schéma créé depuis les modèles : aucune table « inattendue » ni manquante
    (preuve que Base.metadata est chargé), état INCONSISTENT conservé car la
    comparaison exhaustive n'est pas démontrée ; codes 1 et 2 (--strict)."""
    with _temp_postgres("sunu-dbstate-ca", "dbcreateall") as url:
        env = _clean_env(DATABASE_URL=url)
        setup = (
            "import sys; sys.path.insert(0, sys.argv[1]);"
            "from sqlalchemy import create_engine;"
            "from app.db.state_detector import load_model_metadata;"
            "e = create_engine(sys.argv[2]); load_model_metadata().create_all(e); e.dispose()"
        )
        rc, _, err = _run([sys.executable, "-c", setup, str(PROJECT_ROOT), url], env=env, cwd=tmp_path)
        assert rc == 0, err.decode()[-500:]

        rc, out, err = _run_cli("--json", env=env, cwd=tmp_path)
        data = _parse(out)
        assert rc == 1, err
        assert data["status"] == "ok"
        assert data["state"] == "INCONSISTENT_DATABASE"
        assert data["unexpected_objects"] == []
        assert "unexpected_tables" not in data["checks_failed"]
        assert "missing_expected_tables" not in data["checks_failed"]
        assert "missing_expected_enums" not in data["checks_failed"]
        assert "exhaustive_schema_comparison_not_completed" in data["checks_failed"]
        assert set(data["tables_found"]) == _expected_model_tables()

        rc, _, err = _run_cli("--strict", env=env, cwd=tmp_path)
        assert rc == 2, err


# ---------------------------------------------------------------------------
# Sans connexion
# ---------------------------------------------------------------------------

def test_database_url_missing_json_valid(tmp_path):
    # `.env` leurre dans le répertoire courant : s'il était lu, le code serait
    # database_unreachable (port 1) et non database_url_missing.
    (tmp_path / ".env").write_text(f"DATABASE_URL={UNREACHABLE_URL}\nSECRET_KEY=leurre\n")
    env = _clean_env()  # ni DATABASE_URL ni SECRET_KEY
    for args in (("--json",), ("--strict", "--json")):
        rc, out, err = _run_cli(*args, env=env, cwd=tmp_path, timeout=30)
        assert rc == 3, err
        _assert_undetermined(_parse(out), "database_url_missing")


def test_connection_impossible_json_valid(tmp_path):
    env = _clean_env(DATABASE_URL=UNREACHABLE_URL)
    for cwd in (tmp_path, PROJECT_ROOT):
        rc, out, err = _run_cli("--json", env=env, cwd=cwd, timeout=30)
        assert rc == 3, err
        data = _parse(out)
        _assert_undetermined(data, "database_unreachable")
        # Ni identifiants, ni URL, ni message d'exception brut
        for stream in (out, err):
            assert b"nopass-secret" not in stream
            assert b"nouser" not in stream
            assert b"127.0.0.1:1" not in stream


def test_strict_inconsistent_exit_code(tmp_path):
    """Avec --strict, une erreur de détection garde le code 3 (jamais 2) et
    n'est jamais présentée comme INCONSISTENT_DATABASE."""
    env = _clean_env(DATABASE_URL=UNREACHABLE_URL)
    rc, out, err = _run_cli("--strict", "--json", env=env, cwd=tmp_path, timeout=30)
    assert rc == 3, err
    _assert_undetermined(_parse(out), "database_unreachable")

    # Sortie texte : erreur sur stderr, sans fuite d'identifiants
    rc, out, err = _run_cli("--strict", env=env, cwd=tmp_path, timeout=30)
    assert rc == 3
    assert b"database_unreachable" in err
    assert b"nopass-secret" not in out + err


def test_invalid_database_url_json_valid(tmp_path):
    env = _clean_env(DATABASE_URL="pas-une-url-secret")
    rc, out, err = _run_cli("--json", env=env, cwd=tmp_path, timeout=30)
    assert rc == 3, err
    _assert_undetermined(_parse(out), "database_url_invalid")
    assert b"pas-une-url-secret" not in out + err


def test_model_metadata_loaded_without_settings(tmp_path):
    """Les modèles sont chargés sans app.core.config (donc sans .env ni
    SECRET_KEY), sans connexion, et sans laisser de module substitué."""
    probe = (
        "import json, sys; sys.path.insert(0, sys.argv[1]);"
        "from app.db.state_detector import load_model_metadata, _expected_enums;"
        "md = load_model_metadata();"
        "print(json.dumps({'tables': sorted(md.tables), 'enums': sorted(_expected_enums(md)),"
        " 'leaked': sorted(m for m in sys.modules if m == 'app.db.session' or m.startswith('app.modules') or m.startswith('app.core'))}))"
    )
    (tmp_path / ".env").write_text("DATABASE_URL=postgresql://x@127.0.0.1:1/x\n")
    rc, out, err = _run([sys.executable, "-c", probe, str(PROJECT_ROOT)], env=_clean_env(), cwd=tmp_path, timeout=30)
    assert rc == 0, err.decode()[-500:]
    data = json.loads(out)
    from app.db.session import Base
    from app.db.state_detector import _expected_enums
    assert set(data["tables"]) == _expected_model_tables() and data["tables"]
    assert set(data["enums"]) == _expected_enums(Base.metadata) and data["enums"]
    assert data["leaked"] == []


def test_model_metadata_in_process_uses_real_base():
    from app.db.session import Base
    from app.db.state_detector import load_model_metadata
    assert load_model_metadata() is Base.metadata


# ---------------------------------------------------------------------------
# Erreurs de lecture (mocks ciblés : aucune base n'est modifiée ni contactée)
# ---------------------------------------------------------------------------

# Message brut factice du pilote : il ne doit jamais apparaître dans le résultat.
_DRIVER_SECRET = "FATAL password=pilote-secret host=db.interne.example"
_FAKE_URL = "postgresql://fakeuser:url-secret@db.interne.example:5432/fakedb"

_SQL_ENUMS = "pg_type"
_SQL_ALEMBIC = "alembic_version"


def _driver_error():
    from sqlalchemy.exc import ProgrammingError
    return ProgrammingError("SELECT ...", {}, Exception(_DRIVER_SECRET))


class _FakeResult:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def fetchall(self):
        return list(self._rows)

    def scalar(self):
        return self._scalar


class _FakeConn:
    """Connexion factice : répond aux seules requêtes du détecteur et
    enregistre tout ce qui est exécuté."""

    def __init__(self, enums=(), alembic_rows=None, fail=()):
        self.enums = list(enums)
        self.alembic_rows = alembic_rows
        self.fail = set(fail)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, stmt):
        sql = str(stmt)
        self.executed.append(sql)
        if sql == "BEGIN READ ONLY":
            return _FakeResult()
        if sql == "SHOW transaction_read_only":
            return _FakeResult(scalar="on")
        if _SQL_ENUMS in sql:
            if "enums" in self.fail:
                raise _driver_error()
            return _FakeResult(rows=[(e,) for e in self.enums])
        if _SQL_ALEMBIC in sql:
            if "alembic" in self.fail:
                raise _driver_error()
            return _FakeResult(rows=self.alembic_rows or [])
        raise AssertionError(f"Requête inattendue du détecteur: {sql}")


class _FakeEngine:
    def __init__(self, conn):
        self.conn = conn

    def connect(self):
        return self.conn

    def dispose(self):
        pass


class _FakeInspector:
    def __init__(self, tables, fail):
        self.tables = tables
        self.fail = fail

    def get_table_names(self, schema=None):
        assert schema == "public"
        if self.fail:
            raise _driver_error()
        return list(self.tables)


def _detect_with_fakes(monkeypatch, *, tables=(), fail=(), **conn_kwargs):
    from app.db import state_detector as sd

    conn = _FakeConn(fail=fail, **conn_kwargs)
    monkeypatch.setattr(sd, "create_engine", lambda *a, **k: _FakeEngine(conn))
    monkeypatch.setattr(sd, "inspect", lambda c: _FakeInspector(tables, "tables" in fail))
    result = sd.detect_state(_FAKE_URL)
    return result, result.to_dict(), conn


def _assert_read_failed(data, step):
    assert set(data) == set(RESULT_KEYS)
    assert data["status"] == "error"
    assert data["state"] is None
    assert data["error"]["code"] == "database_read_failed"
    assert data["error"]["message"]
    assert data["details"]["step"] == step
    assert data["details"]["exception_type"] == "ProgrammingError"
    assert data["checks_failed"] == ["database_read_failed", step]
    # Lecture seule bien confirmée avant l'échec
    assert "begin_read_only" in data["checks_passed"]
    assert data["read_only_enforced"] is True
    dumped = json.dumps(data, ensure_ascii=False)
    for secret in ("pilote-secret", "db.interne.example", "url-secret", "fakeuser", _DRIVER_SECRET):
        assert secret not in dumped


def test_read_error_tables_is_undetermined(monkeypatch):
    _, data, conn = _detect_with_fakes(monkeypatch, fail={"tables"})
    _assert_read_failed(data, "inspect_tables")
    # Aucune lecture n'est poursuivie sur une transaction potentiellement interrompue
    assert not any(_SQL_ENUMS in q or _SQL_ALEMBIC in q for q in conn.executed)


def test_read_error_enums_is_undetermined(monkeypatch):
    # Base « vide » côté tables : sans le correctif, ce cas donnait FRESH_DATABASE.
    _, data, conn = _detect_with_fakes(monkeypatch, tables=[], fail={"enums"})
    _assert_read_failed(data, "read_enums")
    assert not any(_SQL_ALEMBIC in q for q in conn.executed)


def test_read_error_alembic_version_is_undetermined(monkeypatch):
    _, data, _ = _detect_with_fakes(
        monkeypatch, tables=["alembic_version", "users"], fail={"alembic"}
    )
    _assert_read_failed(data, "read_alembic_version")


def test_empty_database_mocked_is_fresh(monkeypatch):
    """Lecture réussie sans table ni ENUM : FRESH_DATABASE (absence ≠ erreur)."""
    _, data, conn = _detect_with_fakes(monkeypatch, tables=[], enums=[])
    assert set(data) == set(RESULT_KEYS)
    assert data["status"] == "ok"
    assert data["error"] is None
    assert data["state"] == "FRESH_DATABASE"
    assert data["details"]["enums_found"] == []
    assert data["read_only_enforced"] is True
    # alembic_version absente : jamais interrogée
    assert not any(_SQL_ALEMBIC in q for q in conn.executed)


def test_empty_alembic_version_table_behaviour_unchanged(monkeypatch):
    """Table alembic_version existante mais vide : comportement inchangé
    (révision None, INCONSISTENT_DATABASE, pas une erreur de lecture)."""
    _, data, _ = _detect_with_fakes(
        monkeypatch, tables=["alembic_version", "users"], alembic_rows=[]
    )
    assert data["status"] == "ok"
    assert data["state"] == "INCONSISTENT_DATABASE"
    assert data["declared_alembic_revision"] is None
    assert "alembic_version_invalid" in data["checks_failed"]
    assert "read_alembic_version" in data["checks_passed"]


def test_only_read_statements_sent(monkeypatch):
    _, _, conn = _detect_with_fakes(
        monkeypatch, tables=["alembic_version", "users"], alembic_rows=[("abc",)]
    )
    assert conn.executed[:2] == ["BEGIN READ ONLY", "SHOW transaction_read_only"]
    for q in conn.executed[2:]:
        assert q.lstrip().upper().startswith("SELECT"), q


def _load_cli_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("db_state_cli", DB_STATE_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_exit_codes_unchanged_for_read_errors(monkeypatch):
    cli = _load_cli_module()
    _, read_error, _ = _detect_with_fakes(monkeypatch, fail={"enums"})
    assert cli.exit_code(read_error, strict=False) == 3
    assert cli.exit_code(read_error, strict=True) == 3
    # Codes existants inchangés pour les états détectés
    for state, normal, strict in (
        ("FRESH_DATABASE", 0, 0),
        ("CREATE_ALL_INITIALIZED", 0, 2),
        ("ALEMBIC_MANAGED", 0, 2),
        ("INCONSISTENT_DATABASE", 1, 2),
    ):
        out = {**read_error, "status": "ok", "error": None, "state": state}
        assert cli.exit_code(out, strict=False) == normal, state
        assert cli.exit_code(out, strict=True) == strict, state


def test_json_keys_identical_across_results(monkeypatch):
    from app.db.state_detector import detect_state
    results = [
        _detect_with_fakes(monkeypatch, fail={"tables"})[1],
        _detect_with_fakes(monkeypatch, fail={"enums"})[1],
        _detect_with_fakes(monkeypatch, tables=["alembic_version", "x"], fail={"alembic"})[1],
        _detect_with_fakes(monkeypatch, tables=[])[1],
        _detect_with_fakes(monkeypatch, tables=["alembic_version", "x"], alembic_rows=[])[1],
    ]
    monkeypatch.undo()
    results.append(detect_state("pas-une-url").to_dict())
    monkeypatch.delenv("DATABASE_URL", raising=False)
    results.append(detect_state(None).to_dict())
    cli_fallback = _load_cli_module()._fallback_error(RuntimeError())
    for data in results + [cli_fallback]:
        assert list(data) == list(results[0])
        assert set(data) == set(RESULT_KEYS)
        json.loads(json.dumps(data))  # sérialisable


# ---------------------------------------------------------------------------
# Intégration : lecture seule effective côté serveur
# ---------------------------------------------------------------------------

def _pg_dump(container, db):
    rc, out, err = _run(f"docker exec {container} pg_dump -U u -d {db} --no-owner", timeout=60)
    assert rc == 0, err.decode()[-300:]
    # \restrict / \unrestrict contiennent une clé aléatoire à chaque dump
    return "\n".join(
        line for line in out.decode().splitlines()
        if not line.startswith(("\\restrict", "\\unrestrict"))
    )


@pytest.mark.integration
def test_writes_refused_during_detector_transaction(monkeypatch, tmp_path):
    """Pendant la transaction du détecteur, le serveur refuse toute écriture
    (SQLSTATE 25006) ; après détection, la base est strictement identique."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import DBAPIError
    from app.db import state_detector as sd

    with _temp_postgres_container("sunu-dbstate-ro", "dbreadonly") as (container, url):
        head, _ = sd._get_project_head_and_revisions()
        setup = create_engine(url)
        try:
            sd.load_model_metadata().create_all(setup)
            with setup.begin() as c:
                c.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
                c.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": head or "none"})
        finally:
            setup.dispose()

        before = _pg_dump(container, "dbreadonly")

        attempts = {}
        original_get_enums = sd._get_enums

        def probing_get_enums(conn):
            attempts["read_only"] = conn.execute(text("SHOW transaction_read_only")).scalar()
            for label, stmt in (
                ("create", "CREATE TABLE detector_write_probe (id int)"),
                ("insert", "INSERT INTO alembic_version VALUES ('probe')"),
                ("update", "UPDATE alembic_version SET version_num = 'probe'"),
                ("delete", "DELETE FROM alembic_version"),
            ):
                conn.execute(text("SAVEPOINT write_probe"))
                try:
                    conn.execute(text(stmt))
                except DBAPIError as exc:
                    attempts[label] = getattr(exc.orig, "pgcode", None)
                else:
                    attempts[label] = "ACCEPTED"
                conn.execute(text("ROLLBACK TO SAVEPOINT write_probe"))
            return original_get_enums(conn)

        monkeypatch.setattr(sd, "_get_enums", probing_get_enums)
        result = sd.detect_state(url).to_dict()
        monkeypatch.undo()

        assert attempts["read_only"] == "on"
        for label in ("create", "insert", "update", "delete"):
            assert attempts[label] == "25006", (label, attempts[label])  # read_only_sql_transaction
        assert result["status"] == "ok"
        assert result["read_only_enforced"] is True
        assert result["declared_alembic_revision"] == (head or "none")

        # Exécution normale de la CLI, puis comparaison complète du dump
        rc, out, err = _run_cli("--json", env=_clean_env(DATABASE_URL=url), cwd=tmp_path)
        assert _parse(out)["status"] == "ok", err
        after = _pg_dump(container, "dbreadonly")
        assert after == before
        assert "detector_write_probe" not in after
