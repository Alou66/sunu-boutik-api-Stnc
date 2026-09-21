"""Caractérise la réinitialisation du mot de passe par e-mail + code temporaire
à usage unique (étape 0.1.1), qui remplace le flux par numéro de téléphone.

  POST /auth/forgot-password/request  {email}                     -> 200 (réponse générique)
  POST /auth/forgot-password/confirm  {email, code, new_password} -> 204

Le code n'est jamais retourné en HTTP : il part par e-mail (core/email.py,
send_email est capturé ici) et n'est stocké qu'en HMAC (users.reset_code_hash).
Les échecs de confirmation (code faux, expiré, déjà utilisé, épuisé, absent de
la base, compte inconnu) répondent tous par le même 400, pour ne révéler ni
l'existence d'un compte ni l'état de son code.

Réf. app/modules/identity/identity_service.py::request_password_reset /
confirm_password_reset.
"""
import logging
import re
import threading
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app

OLD_PASSWORD = "Test1234!"
NEW_PASSWORD = "NouveauMdp1"
GENERIC_INVALID = "Code invalide ou expiré. Demandez un nouveau code."


@pytest.fixture
def outbox(monkeypatch):
    """Capture les e-mails au niveau de core.email.send_email (le vrai gabarit du
    message est donc exercé) et permet d'en extraire le code."""
    sent = []

    def fake_send_email(to_email, to_name, subject, html_content):
        sent.append({"to": to_email, "name": to_name, "subject": subject, "html": html_content})

    monkeypatch.setattr("app.core.email.send_email", fake_send_email)

    class Outbox:
        messages = sent

        @staticmethod
        def last_code():
            match = re.search(r">(\d{6})<", sent[-1]["html"])
            assert match, "aucun code à 6 chiffres dans l'e-mail"
            return match.group(1)

    return Outbox


def _request_code(client, email):
    return client.post("/auth/forgot-password/request", json={"email": email})


def _confirm(client, email, code, new_password=NEW_PASSWORD):
    return client.post(
        "/auth/forgot-password/confirm",
        json={"email": email, "code": code, "new_password": new_password},
    )


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


def _wrong_code(real_code):
    return "000000" if real_code != "000000" else "111111"


# ---- Demande de code ----


def test_request_with_known_email_sends_code_by_email_only(client, db_session, owner, outbox):
    resp = _request_code(client, owner.email)

    assert resp.status_code == 200
    assert len(outbox.messages) == 1
    assert outbox.messages[0]["to"] == owner.email
    code = outbox.last_code()
    assert re.fullmatch(r"\d{6}", code)

    # Le code n'est jamais dans la réponse HTTP (corps ni en-têtes).
    assert code not in resp.text
    assert code not in str(dict(resp.headers))
    assert set(resp.json()) == {"message"}


def test_request_stores_only_a_hash_with_short_expiry(client, db_session, owner, outbox):
    _request_code(client, owner.email)
    code = outbox.last_code()

    db_session.refresh(owner)
    assert owner.reset_code_hash is not None
    assert re.fullmatch(r"[0-9a-f]{64}", owner.reset_code_hash)
    assert code not in owner.reset_code_hash
    assert owner.reset_code_hash != code
    remaining = owner.reset_code_expires_at - datetime.utcnow()
    assert timedelta(minutes=14) < remaining <= timedelta(minutes=15)
    assert owner.reset_code_attempts == 0


def test_request_with_unknown_email_gives_same_response_and_sends_nothing(client, owner, outbox):
    known = _request_code(client, owner.email)
    unknown = _request_code(client, "inconnu@example.com")

    assert unknown.status_code == known.status_code == 200
    assert unknown.json() == known.json()
    assert [m["to"] for m in outbox.messages] == [owner.email]  # rien pour l'inconnu


def test_request_for_inactive_account_sends_nothing_but_answers_the_same(client, db_session, employee, outbox):
    employee.is_active = False
    db_session.commit()

    resp = _request_code(client, employee.email)

    assert resp.status_code == 200
    assert outbox.messages == []


def test_request_for_admin_account_sends_a_code_like_any_other_role(client, admin_user, outbox):
    # Le superadmin (plateforme) est un `users` comme les autres, avec sa propre
    # connexion (login_admin) mais le même mécanisme de récupération de mot de
    # passe que owner/employee : aucune raison de l'en priver s'il l'oublie.
    resp = _request_code(client, admin_user.email)

    assert resp.status_code == 200
    assert [m["to"] for m in outbox.messages] == [admin_user.email]


def test_request_within_cooldown_does_not_send_a_second_email(client, owner, outbox):
    _request_code(client, owner.email)
    resp = _request_code(client, owner.email)

    assert resp.status_code == 200
    assert len(outbox.messages) == 1


def test_new_request_invalidates_the_previous_code(client, db_session, owner, outbox):
    _request_code(client, owner.email)
    first_code = outbox.last_code()
    db_session.refresh(owner)
    owner.reset_code_expires_at = datetime.utcnow() + timedelta(minutes=13)  # émis il y a > 60 s
    db_session.commit()

    _request_code(client, owner.email)
    assert len(outbox.messages) == 2
    second_code = outbox.last_code()

    if first_code != second_code:
        assert _confirm(client, owner.email, first_code).status_code == 400
    assert _confirm(client, owner.email, second_code).status_code == 204


def test_request_with_invalid_email_format_is_rejected(client):
    assert client.post("/auth/forgot-password/request", json={"email": "pas-un-email"}).status_code == 422


# ---- Confirmation : succès ----


def test_valid_code_changes_password_and_old_password_is_refused(client, owner, outbox):
    _request_code(client, owner.email)

    resp = _confirm(client, owner.email, outbox.last_code())

    assert resp.status_code == 204
    assert resp.content == b""
    assert _login(client, owner.email, NEW_PASSWORD).status_code == 200
    assert _login(client, owner.email, OLD_PASSWORD).status_code == 401


def test_reset_clears_must_change_password_and_the_code_state(client, db_session, owner, outbox):
    owner.must_change_password = True
    db_session.commit()
    _request_code(client, owner.email)

    assert _confirm(client, owner.email, outbox.last_code()).status_code == 204

    db_session.refresh(owner)
    assert owner.must_change_password is False
    assert owner.reset_code_hash is None
    assert owner.reset_code_expires_at is None
    assert owner.reset_code_attempts == 0


def test_reset_works_for_an_employee_too(client, employee, outbox):
    _request_code(client, employee.email)

    assert _confirm(client, employee.email, outbox.last_code()).status_code == 204
    assert _login(client, employee.email, NEW_PASSWORD).status_code == 200


# ---- Confirmation : échecs ----


def test_wrong_code_is_refused_and_password_unchanged(client, db_session, owner, outbox):
    _request_code(client, owner.email)
    code = outbox.last_code()

    resp = _confirm(client, owner.email, _wrong_code(code))

    assert resp.status_code == 400
    assert resp.json()["detail"] == GENERIC_INVALID
    assert _login(client, owner.email, OLD_PASSWORD).status_code == 200
    assert _login(client, owner.email, NEW_PASSWORD).status_code == 401
    db_session.refresh(owner)
    assert owner.reset_code_attempts == 1
    assert owner.reset_code_hash is not None  # le vrai code reste utilisable


def test_expired_code_is_refused_and_password_unchanged(client, db_session, owner, outbox):
    _request_code(client, owner.email)
    code = outbox.last_code()
    db_session.refresh(owner)
    owner.reset_code_expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()

    resp = _confirm(client, owner.email, code)

    assert resp.status_code == 400
    assert resp.json()["detail"] == GENERIC_INVALID
    assert _login(client, owner.email, OLD_PASSWORD).status_code == 200
    db_session.refresh(owner)
    assert owner.reset_code_hash is None  # code expiré nettoyé


def test_code_cannot_be_used_twice(client, owner, outbox):
    _request_code(client, owner.email)
    code = outbox.last_code()
    assert _confirm(client, owner.email, code, "PremierMdp1").status_code == 204

    second = _confirm(client, owner.email, code, "DeuxiemeMdp1")

    assert second.status_code == 400
    assert second.json()["detail"] == GENERIC_INVALID
    assert _login(client, owner.email, "PremierMdp1").status_code == 200
    assert _login(client, owner.email, "DeuxiemeMdp1").status_code == 401


def test_confirm_without_any_requested_code_is_refused(client, owner):
    resp = _confirm(client, owner.email, "123456")

    assert resp.status_code == 400
    assert resp.json()["detail"] == GENERIC_INVALID
    assert _login(client, owner.email, OLD_PASSWORD).status_code == 200


def test_confirm_with_missing_code_field_is_rejected(client, owner):
    resp = client.post(
        "/auth/forgot-password/confirm", json={"email": owner.email, "new_password": NEW_PASSWORD}
    )
    assert resp.status_code == 422


def test_confirm_with_empty_code_is_refused(client, owner, outbox):
    _request_code(client, owner.email)

    resp = _confirm(client, owner.email, "")

    assert resp.status_code == 400
    assert resp.json()["detail"] == GENERIC_INVALID


def test_confirm_for_unknown_user_is_indistinguishable_from_wrong_code(client, owner, outbox):
    _request_code(client, owner.email)
    wrong_for_known = _confirm(client, owner.email, _wrong_code(outbox.last_code()))
    unknown = _confirm(client, "inconnu@example.com", "123456")

    assert unknown.status_code == wrong_for_known.status_code == 400
    assert unknown.json() == wrong_for_known.json()


def test_code_of_one_user_does_not_work_for_another(client, owner, employee, outbox):
    _request_code(client, owner.email)
    owner_code = outbox.last_code()
    _request_code(client, employee.email)

    if owner_code != outbox.last_code():
        assert _confirm(client, employee.email, owner_code).status_code == 400
    assert _login(client, employee.email, OLD_PASSWORD).status_code == 200


def test_too_short_new_password_is_refused_without_consuming_the_code(client, owner, outbox):
    _request_code(client, owner.email)
    code = outbox.last_code()

    short = _confirm(client, owner.email, code, "abc")
    assert short.status_code == 400
    assert "mot de passe" in short.json()["detail"]

    assert _confirm(client, owner.email, code).status_code == 204


def test_too_many_wrong_attempts_burn_the_code_even_for_the_right_one(client, db_session, owner, outbox):
    _request_code(client, owner.email)
    code = outbox.last_code()
    wrong = _wrong_code(code)

    for _ in range(5):
        assert _confirm(client, owner.email, wrong).status_code == 400

    # Le bon code est désormais refusé : il faut en redemander un.
    refused = _confirm(client, owner.email, code)
    assert refused.status_code == 400
    assert refused.json()["detail"] == GENERIC_INVALID
    assert _login(client, owner.email, OLD_PASSWORD).status_code == 200

    _request_code(client, owner.email)
    assert len(outbox.messages) == 2
    assert _confirm(client, owner.email, outbox.last_code()).status_code == 204


def test_fewer_wrong_attempts_than_the_limit_still_allow_the_right_code(client, owner, outbox):
    _request_code(client, owner.email)
    code = outbox.last_code()
    for _ in range(4):
        assert _confirm(client, owner.email, _wrong_code(code)).status_code == 400

    assert _confirm(client, owner.email, code).status_code == 204


def test_concurrent_confirmations_with_the_same_code_succeed_only_once(client, owner, outbox):
    _request_code(client, owner.email)
    code = outbox.last_code()
    results = {}
    barrier = threading.Barrier(2)

    def _confirm_in_thread(index, password):
        with TestClient(app) as local_client:
            barrier.wait(timeout=5)
            results[index] = _confirm(local_client, owner.email, code, password)

    threads = [
        threading.Thread(target=_confirm_in_thread, args=(0, "MotDePasseA1")),
        threading.Thread(target=_confirm_in_thread, args=(1, "MotDePasseB1")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert sorted(r.status_code for r in results.values()) == [204, 400], {i: r.text for i, r in results.items()}
    winner = "MotDePasseA1" if results[0].status_code == 204 else "MotDePasseB1"
    loser = "MotDePasseB1" if winner == "MotDePasseA1" else "MotDePasseA1"
    assert _login(client, owner.email, winner).status_code == 200
    assert _login(client, owner.email, loser).status_code == 401


# ---- Rate limiting, secrets et anciennes routes ----


def test_request_route_is_rate_limited(client, owner, outbox):
    statuses = [_request_code(client, owner.email).status_code for _ in range(6)]

    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429


def test_confirm_route_is_rate_limited(client, owner):
    statuses = [_confirm(client, owner.email, "123456").status_code for _ in range(11)]

    assert statuses[:10] == [400] * 10
    assert statuses[10] == 429


def test_code_and_password_never_appear_in_responses_or_logs(client, owner, monkeypatch, caplog):
    # SMTP non configuré (conftest) : le vrai send_email s'exécute et logge un warning.
    monkeypatch.setattr("app.modules.identity.identity_service.generate_reset_code", lambda: "731942")
    caplog.set_level(logging.DEBUG)

    requested = _request_code(client, owner.email)
    wrong = _confirm(client, owner.email, "555555", "MotDePasseSecret9")
    confirmed = _confirm(client, owner.email, "731942", "MotDePasseSecret9")

    assert (requested.status_code, wrong.status_code, confirmed.status_code) == (200, 400, 204)
    for response in (requested, wrong, confirmed):
        assert "731942" not in response.text and "MotDePasseSecret9" not in response.text
    assert "731942" not in caplog.text
    assert "555555" not in caplog.text
    assert "MotDePasseSecret9" not in caplog.text
    assert "SMTP non configuré" in caplog.text  # le chemin d'envoi a bien été exercé


def test_reset_code_fields_are_not_exposed_in_public_dto(client, auth_headers, owner, outbox):
    _request_code(client, owner.email)

    user = client.get("/auth/me", headers=auth_headers).json()["user"]

    assert not any(key.startswith("reset_code") for key in user)
    assert "token_version" not in user and "hashed_password" not in user


# ---- Parité complète pour le superadmin (rôle ADMIN) ----


def _login_admin(client, email, password):
    return client.post("/admin/login", json={"email": email, "password": password})


def test_admin_can_reset_forgotten_password_end_to_end(client, admin_user, outbox):
    assert _login_admin(client, admin_user.email, OLD_PASSWORD).status_code == 200

    assert _request_code(client, admin_user.email).status_code == 200
    code = outbox.last_code()

    resp = _confirm(client, admin_user.email, code)

    assert resp.status_code == 204
    assert _login_admin(client, admin_user.email, OLD_PASSWORD).status_code == 401
    assert _login_admin(client, admin_user.email, NEW_PASSWORD).status_code == 200


def test_admin_wrong_code_is_refused_like_any_other_role(client, admin_user, outbox):
    _request_code(client, admin_user.email)
    code = outbox.last_code()

    resp = _confirm(client, admin_user.email, _wrong_code(code))

    assert resp.status_code == 400
    assert resp.json()["detail"] == GENERIC_INVALID
    assert _login_admin(client, admin_user.email, OLD_PASSWORD).status_code == 200


def test_admin_password_reset_invalidates_previously_issued_admin_jwt(client, admin_user, outbox):
    # Même garantie que pour owner/employee (voir test_token_version_invalidation.py) :
    # un JWT émis avant la réinitialisation ne doit plus être accepté après, même
    # sur les routes réservées à l'administrateur (get_current_admin s'appuie sur
    # le même get_current_user que /auth/me).
    old_login = _login_admin(client, admin_user.email, OLD_PASSWORD)
    assert old_login.status_code == 200
    old_headers = {"Authorization": f"Bearer {old_login.json()['access_token']}"}
    assert client.get("/admin/overview", headers=old_headers).status_code == 200

    _request_code(client, admin_user.email)
    assert _confirm(client, admin_user.email, outbox.last_code()).status_code == 204

    revoked = client.get("/admin/overview", headers=old_headers)
    assert revoked.status_code == 401
    assert "reconnecter" in revoked.json()["detail"]

    new_login = _login_admin(client, admin_user.email, NEW_PASSWORD)
    assert new_login.status_code == 200
    new_headers = {"Authorization": f"Bearer {new_login.json()['access_token']}"}
    assert client.get("/admin/overview", headers=new_headers).status_code == 200


def test_legacy_phone_routes_are_disabled_and_do_not_reveal_accounts(client, db_session, owner, shop):
    shop.phone = "771112233"
    db_session.commit()

    known = client.post("/auth/forgot-password/check", json={"phone": "771112233"})
    unknown = client.post("/auth/forgot-password/check", json={"phone": "779999999"})
    reset = client.post("/auth/forgot-password/reset", json={"phone": "771112233", "new_password": NEW_PASSWORD})

    assert known.status_code == unknown.status_code == reset.status_code == 410
    assert known.json() == unknown.json()
    assert "shop_name" not in known.text
    assert _login(client, owner.email, NEW_PASSWORD).status_code == 401
