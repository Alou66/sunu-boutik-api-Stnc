"""Sécurité de l'envoi d'e-mails (lot 1 de l'audit : V1, V2, V3, L4).

  V1  STARTTLS avec vérification du certificat et du nom d'hôte.
  V2  Les liens des e-mails ne dépendent jamais de l'en-tête HTTP Origin.
  V3  Toute donnée dynamique est échappée dans les gabarits HTML.
  L4  En-têtes construits avec email.utils, sans injection CRLF possible.

Aucun test ne contacte de serveur SMTP : smtplib.SMTP est remplacé par un mock
(app.core.email.smtplib.SMTP), et les identifiants utilisés sont factices.
"""
import email
import logging
import smtplib
import socket
import ssl
from email.header import decode_header, make_header
from unittest.mock import patch

import pytest

from app.core import email as email_module
from app.core.config import settings
from app.modules.identity.identity_model import Shop, ShopStatus, User, UserRole

FAKE_SMTP_PASSWORD = "fake-app-password-XYZ987"
FAKE_SMTP_USER = "noreply@sunu-boutik.test"
FRONTEND = "https://app.sunu-boutik.test"
EVIL_ORIGIN = "https://evil.attacker.test"


@pytest.fixture
def smtp_settings(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USER", FAKE_SMTP_USER)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", FAKE_SMTP_PASSWORD)
    monkeypatch.setattr(settings, "SMTP_SENDER_NAME", "Sunu Boutik")
    monkeypatch.setattr(settings, "FRONTEND_URL", FRONTEND)


@pytest.fixture
def smtp_mock(smtp_settings):
    with patch("app.core.email.smtplib.SMTP") as smtp_cls:
        server = smtp_cls.return_value.__enter__.return_value
        yield smtp_cls, server


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    def fake_send_email(to_email, to_name, subject, html_content):
        sent.append({"to": to_email, "name": to_name, "subject": subject, "html": html_content})

    monkeypatch.setattr("app.core.email.send_email", fake_send_email)
    return sent


def _send(to_email="client@example.com", to_name="Awa Diop", subject="Sujet", html_content="<p>ok</p>"):
    email_module.send_email(to_email, to_name, subject, html_content)


def _sent_message(server) -> email.message.Message:
    _sender, _recipients, raw = server.sendmail.call_args.args
    return email.message_from_string(raw)


def _decoded(value: str) -> str:
    return str(make_header(decode_header(value)))


# ---- V1 : TLS ----


def test_starttls_uses_a_context_requiring_a_valid_certificate(smtp_mock):
    _smtp_cls, server = smtp_mock
    _send()

    context = server.starttls.call_args.kwargs["context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_starttls_context_checks_the_hostname(smtp_mock):
    _smtp_cls, server = smtp_mock
    _send()

    context = server.starttls.call_args.kwargs["context"]
    assert context.check_hostname is True
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2


def test_starttls_is_called_once_with_that_context_and_no_other_argument(smtp_mock):
    _smtp_cls, server = smtp_mock
    _send()

    server.starttls.assert_called_once()
    assert server.starttls.call_args.args == ()
    assert set(server.starttls.call_args.kwargs) == {"context"}


def test_ehlo_happens_before_and_after_starttls_then_login_then_send(smtp_mock):
    _smtp_cls, server = smtp_mock
    _send()

    assert [name for name, _args, _kwargs in server.method_calls] == [
        "ehlo",
        "starttls",
        "ehlo",
        "login",
        "sendmail",
    ]


def test_connection_uses_configured_host_port_and_keeps_the_timeout(smtp_mock):
    smtp_cls, _server = smtp_mock
    _send()

    smtp_cls.assert_called_once_with("smtp.example.test", 587, timeout=10)


def test_login_and_sendmail_use_the_right_parameters(smtp_mock):
    _smtp_cls, server = smtp_mock
    _send(to_email="client@example.com", to_name="Awa Diop", subject="Bienvenue", html_content="<p>Bonjour</p>")

    server.login.assert_called_once_with(FAKE_SMTP_USER, FAKE_SMTP_PASSWORD)
    sender, recipients, _raw = server.sendmail.call_args.args
    assert sender == FAKE_SMTP_USER
    assert recipients == ["client@example.com"]

    msg = _sent_message(server)
    assert msg["To"] == "Awa Diop <client@example.com>"
    assert msg["From"] == f"Sunu Boutik <{FAKE_SMTP_USER}>"
    assert _decoded(msg["Subject"]) == "Bienvenue"
    assert msg["Date"]
    assert msg["Message-ID"].endswith("@sunu-boutik.test>")
    html_part = msg.get_payload()[0]
    assert html_part.get_content_type() == "text/html"
    assert html_part.get_content_charset() == "utf-8"
    assert "<p>Bonjour</p>" in html_part.get_payload(decode=True).decode("utf-8")


def test_non_ascii_names_and_subject_are_encoded_and_round_trip(smtp_mock):
    _smtp_cls, server = smtp_mock
    _send(to_name="Propriétaire Ndèye", subject="Votre boutique a été validée")

    msg = _sent_message(server)
    assert _decoded(msg["To"]) == "Propriétaire Ndèye <client@example.com>"
    assert _decoded(msg["Subject"]) == "Votre boutique a été validée"


def test_no_smtp_connection_when_smtp_is_not_configured(smtp_mock, monkeypatch):
    smtp_cls, _server = smtp_mock
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    _send()
    smtp_cls.assert_not_called()


# ---- Gestion des erreurs et logs ----


SMTP_FAILURES = [
    ("login", smtplib.SMTPAuthenticationError(535, f"5.7.8 rejected {FAKE_SMTP_PASSWORD}".encode())),
    ("sendmail", smtplib.SMTPRecipientsRefused({"client@example.com": (550, b"no such user")})),
    ("sendmail", smtplib.SMTPServerDisconnected(f"lost {FAKE_SMTP_PASSWORD}")),
    ("starttls", smtplib.SMTPNotSupportedError("STARTTLS extension not supported by server.")),
    ("starttls", ssl.SSLCertVerificationError(1, f"certificate verify failed {FAKE_SMTP_PASSWORD}")),
    ("ehlo", socket.timeout(f"timed out {FAKE_SMTP_PASSWORD}")),
    ("ehlo", ConnectionResetError(104, "Connection reset by peer")),
]


@pytest.mark.parametrize("method, error", SMTP_FAILURES, ids=lambda v: type(v).__name__ if isinstance(v, BaseException) else v)
def test_smtp_errors_are_handled_without_raising_and_logged(smtp_mock, caplog, method, error):
    _smtp_cls, server = smtp_mock
    getattr(server, method).side_effect = error

    with caplog.at_level(logging.DEBUG, logger="app.core.email"):
        _send()  # ne lève pas : l'appelant (tâche de fond) ne doit pas planter

    assert any(r.levelno == logging.ERROR for r in caplog.records)
    assert type(error).__name__ in caplog.text


def test_tls_failure_never_falls_back_to_plain_login(smtp_mock):
    _smtp_cls, server = smtp_mock
    server.starttls.side_effect = ssl.SSLCertVerificationError(1, "certificate verify failed")
    _send()
    server.login.assert_not_called()
    server.sendmail.assert_not_called()


def test_connection_failure_is_handled(smtp_settings, caplog):
    with patch("app.core.email.smtplib.SMTP", side_effect=socket.timeout("timed out")):
        with caplog.at_level(logging.DEBUG, logger="app.core.email"):
            _send()
    assert "TimeoutError" in caplog.text or "timeout" in caplog.text


@pytest.mark.parametrize("method, error", SMTP_FAILURES, ids=lambda v: type(v).__name__ if isinstance(v, BaseException) else v)
def test_secrets_never_appear_in_logs_even_on_error(smtp_mock, caplog, method, error):
    _smtp_cls, server = smtp_mock
    getattr(server, method).side_effect = error
    secret_html = "<p>Mot de passe temporaire : TmpPass1234</p><span>731942</span>"

    with caplog.at_level(logging.DEBUG):
        _send(html_content=secret_html)

    assert FAKE_SMTP_PASSWORD not in caplog.text
    assert "TmpPass1234" not in caplog.text
    assert "731942" not in caplog.text


def test_secrets_never_appear_in_logs_on_success(smtp_mock, caplog):
    with caplog.at_level(logging.DEBUG):
        email_module.send_password_reset_code_email("Awa", "client@example.com", "731942", 15)
        email_module.send_shop_approved_email("Awa", "client@example.com", "Boutique", "TmpPass1234")
    assert FAKE_SMTP_PASSWORD not in caplog.text
    assert "731942" not in caplog.text
    assert "TmpPass1234" not in caplog.text


# ---- L4 : en-têtes / injection CRLF ----


@pytest.mark.parametrize(
    "malicious_name",
    [
        "Eve\r\nBcc: victim@evil.test",
        "Eve\nBcc: victim@evil.test",
        "Eve\rBcc: victim@evil.test",
        "Eve Bcc: victim@evil.test",
        "Eve\x85Bcc: victim@evil.test",
        "Eve\x00\r\n\r\n<html>injected body</html>",
    ],
)
def test_newlines_in_recipient_name_cannot_inject_headers(smtp_mock, malicious_name):
    _smtp_cls, server = smtp_mock
    _send(to_name=malicious_name)

    _sender, recipients, raw = server.sendmail.call_args.args
    assert recipients == ["client@example.com"]
    msg = email.message_from_string(raw)
    assert msg.get_all("Bcc") is None
    assert len(msg.get_all("To")) == 1
    assert "\n" not in _decoded(msg["To"]) and "\r" not in _decoded(msg["To"])
    assert not any(line.lower().startswith("bcc:") for line in raw.splitlines())
    assert "injected body" not in msg.get_payload()[0].get_payload(decode=True).decode()


def test_newlines_in_subject_and_sender_name_cannot_inject_headers(smtp_mock, monkeypatch):
    _smtp_cls, server = smtp_mock
    monkeypatch.setattr(settings, "SMTP_SENDER_NAME", "Sunu\r\nBcc: x@evil.test")
    _send(subject="Sujet\r\nBcc: y@evil.test")

    raw = server.sendmail.call_args.args[2]
    msg = email.message_from_string(raw)
    assert msg.get_all("Bcc") is None
    assert not any(line.lower().startswith("bcc:") for line in raw.splitlines())


def test_recipient_name_with_special_characters_is_properly_quoted(smtp_mock):
    _smtp_cls, server = smtp_mock
    _send(to_name='Diop, Awa "La Patronne" <evil@evil.test>')

    _sender, recipients, raw = server.sendmail.call_args.args
    assert recipients == ["client@example.com"]
    msg = email.message_from_string(raw)
    addresses = email.utils.getaddresses(msg.get_all("To"))
    assert len(addresses) == 1
    assert addresses[0][1] == "client@example.com"


@pytest.mark.parametrize(
    "bad_address",
    ["client@example.com\r\nBcc: victim@evil.test", "client@example.com\nX: y", "a b@example.com", "pas-une-adresse", "ndèye@example.com"],
)
def test_unsafe_recipient_address_is_never_sent(smtp_mock, caplog, bad_address):
    smtp_cls, server = smtp_mock
    with caplog.at_level(logging.DEBUG, logger="app.core.email"):
        _send(to_email=bad_address)
    smtp_cls.assert_not_called()
    server.sendmail.assert_not_called()
    assert "evil.test" not in caplog.text


# ---- V3 : échappement HTML de chaque gabarit ----


PAYLOAD = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'
ESCAPED_PAYLOAD = "&lt;script&gt;alert(1)&lt;/script&gt;&quot;&gt;&lt;img src=x onerror=alert(2)&gt;"

TEMPLATES = {
    "signup_pending": lambda v: email_module.send_signup_pending_emails(v, v, v),
    "shop_approved": lambda v: email_module.send_shop_approved_email(v, v, v, "TmpPass1234"),
    "shop_suspended": lambda v: email_module.send_shop_suspended_email(v, v, v, v),
    "shop_reactivated": lambda v: email_module.send_shop_reactivated_email(v, v, v),
    "owner_password_reset": lambda v: email_module.send_owner_password_reset_email(v, v, v, "TmpPass1234"),
    "password_reset_code": lambda v: email_module.send_password_reset_code_email(v, v, "123456", 15),
    "shop_rejected": lambda v: email_module.send_shop_rejected_email(v, v, v, v),
}


@pytest.fixture
def with_admin_email(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "admin@sunu-boutik.test")
    monkeypatch.setattr(settings, "FRONTEND_URL", FRONTEND)


@pytest.mark.parametrize("template", TEMPLATES.keys())
def test_malicious_html_is_escaped_in_every_template(outbox, with_admin_email, template):
    TEMPLATES[template](PAYLOAD)

    assert outbox, "aucun e-mail produit"
    for message in outbox:
        html_content = message["html"]
        assert "<script>" not in html_content
        assert "<img src=x" not in html_content
        assert '">' + "<img" not in html_content
        assert ESCAPED_PAYLOAD in html_content
        # Pas de double échappement.
        assert "&amp;lt;" not in html_content
        assert "&amp;quot;" not in html_content


@pytest.mark.parametrize("template", TEMPLATES.keys())
def test_normal_values_still_render_readably(outbox, with_admin_email, template):
    TEMPLATES[template]("Boutique d'Awa & Fils")

    for message in outbox:
        html_content = message["html"]
        assert "Boutique d&#x27;Awa &amp; Fils" in html_content
        assert "&amp;amp;" not in html_content


def test_reason_is_escaped_for_suspension_and_rejection(outbox):
    email_module.send_shop_suspended_email("Awa", "a@example.com", "Boutique", PAYLOAD)
    email_module.send_shop_rejected_email("Awa", "a@example.com", "Boutique", PAYLOAD)
    for message in outbox:
        assert f"<b>Motif :</b> {ESCAPED_PAYLOAD}" in message["html"]


def test_button_url_is_escaped_in_href_attribute(outbox, monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_URL", 'https://app.test/"><script>x</script>')
    email_module.send_shop_reactivated_email("Awa", "a@example.com", "Boutique")
    html_content = outbox[-1]["html"]
    assert "<script>x</script>" not in html_content
    assert 'href="https://app.test/&quot;&gt;&lt;script&gt;x&lt;/script&gt;/login"' in html_content


def test_reset_code_and_temp_password_are_still_displayed(outbox):
    email_module.send_password_reset_code_email("Awa", "a@example.com", "731942", 15)
    email_module.send_shop_approved_email("Awa", "a@example.com", "Boutique", "TmpPass1234")
    assert ">731942<" in outbox[0]["html"]
    assert ">TmpPass1234<" in outbox[1]["html"]


# ---- V2 : l'en-tête Origin n'influence jamais les liens ----


def _hrefs(html_content: str) -> list[str]:
    import re

    return re.findall(r'href="([^"]*)"', html_content)


def _assert_links_use_frontend_url_only(messages):
    assert messages, "aucun e-mail produit"
    for message in messages:
        assert "evil" not in message["html"]
        for href in _hrefs(message["html"]):
            assert href.startswith(FRONTEND + "/"), href


def test_malicious_origin_on_register_does_not_reach_email_links(client, outbox, with_admin_email):
    resp = client.post(
        "/auth/register",
        headers={"Origin": EVIL_ORIGIN},
        json={"shop_name": "Boutique Test", "full_name": "Awa Diop", "email": "awa@example.com"},
    )
    assert resp.status_code == 201
    assert {m["to"] for m in outbox} == {"awa@example.com", "admin@sunu-boutik.test"}
    _assert_links_use_frontend_url_only(outbox)
    hrefs = [h for m in outbox for h in _hrefs(m["html"])]
    assert f"{FRONTEND}/login" in hrefs
    assert f"{FRONTEND}/admin/login" in hrefs


@pytest.fixture
def pending_shop_with_owner(db_session):
    shop = Shop(name="Boutique En Attente", status=ShopStatus.PENDING)
    db_session.add(shop)
    db_session.flush()
    owner = User(
        shop_id=shop.id,
        full_name="Owner Attente",
        email="pending-owner@example.com",
        hashed_password=None,
        role=UserRole.OWNER,
        is_active=False,
    )
    db_session.add(owner)
    db_session.commit()
    return shop.id


def test_malicious_origin_on_admin_routes_does_not_reach_email_links(
    client, admin_headers, outbox, with_admin_email, pending_shop_with_owner
):
    headers = {**admin_headers, "Origin": EVIL_ORIGIN}
    shop_id = pending_shop_with_owner

    assert client.post(f"/admin/shops/{shop_id}/approve", headers=headers).status_code == 200
    assert client.patch(f"/admin/shops/{shop_id}/suspend", headers=headers, json={"reason": "Impayé"}).status_code == 200
    assert client.patch(f"/admin/shops/{shop_id}/reactivate", headers=headers).status_code == 200
    assert client.post(f"/admin/shops/{shop_id}/owner/reset-password", headers=headers).status_code == 200
    assert client.post(f"/admin/shops/{shop_id}/reject", headers=headers, json={"reason": "Doublon"}).status_code == 200

    assert [m["subject"] for m in outbox] == [
        "Votre boutique a été validée",
        "Votre boutique a été suspendue",
        "Votre boutique a été réactivée",
        "Votre mot de passe a été réinitialisé",
        "Votre demande n'a pas été validée",
    ]
    _assert_links_use_frontend_url_only(outbox)
    hrefs = [h for m in outbox for h in _hrefs(m["html"])]
    assert f"{FRONTEND}/login" in hrefs
    assert f"{FRONTEND}/register" in hrefs


def test_email_functions_no_longer_accept_a_caller_supplied_frontend_url():
    import inspect

    for fn in (
        email_module.send_signup_pending_emails,
        email_module.send_shop_approved_email,
        email_module.send_shop_suspended_email,
        email_module.send_shop_reactivated_email,
        email_module.send_owner_password_reset_email,
        email_module.send_shop_rejected_email,
    ):
        assert "frontend_url" not in inspect.signature(fn).parameters, fn.__name__
