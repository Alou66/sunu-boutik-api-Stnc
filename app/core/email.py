import html
import logging
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid

from app.core.config import settings

logger = logging.getLogger(__name__)

BRAND_COLOR = "#2563eb"
SMTP_TIMEOUT_SECONDS = 10

# Caractères de contrôle C0 et DEL : jamais acceptables dans un en-tête.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _e(value: object) -> str:
    """Échappe une donnée dynamique pour l'insérer dans du HTML (contenu ou
    attribut). Appliqué UNE seule fois, au moment de l'insertion dans le gabarit :
    les paramètres reçus par les fonctions send_* sont toujours des valeurs brutes."""
    return html.escape(str(value), quote=True)


def _header_safe(value: str) -> str:
    """Neutralise toute tentative d'injection d'en-tête (CRLF) : tous les
    séparateurs de ligne / espaces Unicode (\\r, \\n, \\x85, \\u2028…) et les
    caractères de contrôle sont remplacés par un espace simple."""
    return " ".join(_CONTROL_CHARS.sub(" ", value or "").split())


def _is_safe_address(address: str) -> bool:
    # Les adresses arrivent déjà validées par EmailStr ; on refuse en plus tout
    # ce qui pourrait casser un en-tête (espace, CR/LF, contrôle) ou que
    # formataddr/sendmail ne savent pas encoder (non-ASCII).
    if not address or not address.isascii() or address.count("@") != 1:
        return False
    return not any(ch.isspace() or _CONTROL_CHARS.match(ch) for ch in address)


def _frontend_url() -> str:
    # Les liens des e-mails ne dépendent JAMAIS de la requête HTTP (en-tête
    # Origin falsifiable par n'importe quel client) : seule la configuration
    # serveur fait foi.
    return settings.FRONTEND_URL.rstrip("/")


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    # Valeurs par défaut de create_default_context, réaffirmées explicitement :
    # la vérification du certificat et du nom d'hôte ne doit jamais être désactivée.
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def _layout(title: str, intro: str, body_html: str, button_label: str | None = None, button_url: str | None = None) -> str:
    # `title`, `intro` et `body_html` sont du HTML déjà construit par l'appelant,
    # qui a échappé chaque donnée dynamique. `button_label` et `button_url` sont
    # des valeurs brutes, échappées ici.
    button_html = ""
    if button_label and button_url:
        button_html = f"""
        <tr>
          <td align="center" style="padding: 28px 0 8px 0;">
            <a href="{_e(button_url)}"
               style="background-color:{BRAND_COLOR}; color:#ffffff; text-decoration:none;
                      font-family:Arial, Helvetica, sans-serif; font-size:15px; font-weight:bold;
                      padding:14px 32px; border-radius:8px; display:inline-block;">
              {_e(button_label)}
            </a>
          </td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="fr">
    <body style="margin:0; padding:0; background-color:#f3f4f6; font-family:Arial, Helvetica, sans-serif;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f3f4f6; padding:32px 0;">
        <tr>
          <td align="center">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px; background-color:#ffffff; border-radius:12px; overflow:hidden;">
              <tr>
                <td style="background-color:{BRAND_COLOR}; padding:24px 32px;">
                  <span style="color:#ffffff; font-size:18px; font-weight:bold;">Sunu Boutik</span>
                </td>
              </tr>
              <tr>
                <td style="padding:32px;">
                  <h1 style="margin:0 0 12px 0; font-size:20px; color:#111827;">{title}</h1>
                  <p style="margin:0 0 16px 0; font-size:14px; color:#6b7280; line-height:1.6;">{intro}</p>
                  <div style="font-size:14px; color:#374151; line-height:1.6;">{body_html}</div>
                </td>
              </tr>
              {button_html}
              <tr>
                <td style="padding:24px 32px 32px 32px;">
                  <hr style="border:none; border-top:1px solid #e5e7eb; margin:0 0 16px 0;" />
                  <p style="margin:0; font-size:12px; color:#9ca3af;">
                    Sunu Boutik — Plateforme de gestion pour boutiquiers au Sénégal.
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """


def send_email(to_email: str, to_name: str, subject: str, html_content: str) -> None:
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("SMTP non configuré, email non envoyé à %s", to_email)
        return

    if not _is_safe_address(to_email):
        logger.error("Adresse destinataire invalide, email non envoyé")
        return

    sender = settings.SMTP_USER
    message = MIMEMultipart("alternative")
    message["Subject"] = _header_safe(subject)
    message["From"] = formataddr((_header_safe(settings.SMTP_SENDER_NAME), sender))
    message["To"] = formataddr((_header_safe(to_name), to_email))
    message["Date"] = formatdate(usegmt=True)
    message["Message-ID"] = make_msgid(domain=sender.rpartition("@")[2] or None)
    message.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as server:
            server.ehlo()
            server.starttls(context=_ssl_context())
            server.ehlo()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(sender, [to_email], message.as_string())
    except smtplib.SMTPException as exc:
        # Seuls le type et le code SMTP sont journalisés : le message d'erreur
        # du serveur peut reprendre des éléments de la session.
        logger.error(
            "Echec envoi email SMTP à %s: %s (code=%s)",
            to_email,
            type(exc).__name__,
            getattr(exc, "smtp_code", None),
        )
    except OSError as exc:
        # Inclut ssl.SSLError / SSLCertVerificationError (certificat invalide)
        # et les timeouts réseau.
        logger.error("Erreur réseau lors de l'envoi de l'email: %s (errno=%s)", type(exc).__name__, exc.errno)


def send_signup_pending_emails(shop_name: str, owner_name: str, owner_email: str) -> None:
    base_url = _frontend_url()
    client_html = _layout(
        title="Votre demande est en cours de traitement",
        intro=f"Bonjour {_e(owner_name)},",
        body_html=(
            f"<p>Votre demande de création de la boutique <b>{_e(shop_name)}</b> a bien été reçue.</p>"
            "<p>Elle est actuellement <b>en cours de traitement</b> par notre équipe. "
            "Vous recevrez un email dès que votre compte sera validé. "
            "Vous ne pourrez pas vous connecter avant cette validation.</p>"
        ),
        button_label="Accéder à la page de connexion",
        button_url=f"{base_url}/login",
    )
    send_email(owner_email, owner_name, "Votre demande est en cours de traitement", client_html)

    if settings.ADMIN_EMAIL:
        admin_html = _layout(
            title="Nouvelle demande de boutique à valider",
            intro="Une nouvelle boutique attend votre validation.",
            body_html=(
                "<table role='presentation' width='100%' cellpadding='6' cellspacing='0' style='font-size:14px;'>"
                f"<tr><td style='color:#6b7280;'>Boutique</td><td style='font-weight:bold;'>{_e(shop_name)}</td></tr>"
                f"<tr><td style='color:#6b7280;'>Propriétaire</td><td style='font-weight:bold;'>{_e(owner_name)}</td></tr>"
                f"<tr><td style='color:#6b7280;'>Email</td><td style='font-weight:bold;'>{_e(owner_email)}</td></tr>"
                "</table>"
            ),
            button_label="Ouvrir le dashboard admin",
            button_url=f"{base_url}/admin/login",
        )
        send_email(settings.ADMIN_EMAIL, "Admin", "Nouvelle demande de boutique à valider", admin_html)


def _credentials_box(heading: str, email: str, temp_password: str) -> str:
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="background-color:#f3f4f6; border-radius:8px; margin:16px 0;">
      <tr>
        <td style="padding:16px 20px;">
          <p style="margin:0 0 8px 0; font-size:12px; color:#6b7280; text-transform:uppercase; letter-spacing:0.05em;">
            {heading}
          </p>
          <p style="margin:0 0 4px 0; font-size:14px; color:#111827;">
            <b>Email :</b> {_e(email)}
          </p>
          <p style="margin:0; font-size:14px; color:#111827;">
            <b>Mot de passe temporaire :</b>
            <span style="font-family:monospace; background-color:#fff; border:1px solid #e5e7eb; padding:2px 8px; border-radius:4px;">{_e(temp_password)}</span>
          </p>
        </td>
      </tr>
    </table>
    """


def send_shop_approved_email(owner_name: str, owner_email: str, shop_name: str, temp_password: str) -> None:
    html_content = _layout(
        title="Votre boutique a été validée 🎉",
        intro=f"Bonjour {_e(owner_name)},",
        body_html=(
            f"<p>Bonne nouvelle ! Votre boutique <b>{_e(shop_name)}</b> a été validée.</p>"
            f"{_credentials_box('Vos identifiants de connexion', owner_email, temp_password)}"
            "<p>Pour votre sécurité, il vous sera demandé de choisir un nouveau mot de passe "
            "dès votre première connexion.</p>"
        ),
        button_label="Se connecter maintenant",
        button_url=f"{_frontend_url()}/login",
    )
    send_email(owner_email, owner_name, "Votre boutique a été validée", html_content)


def send_shop_suspended_email(owner_name: str, owner_email: str, shop_name: str, reason: str | None = None) -> None:
    reason_html = f"<p><b>Motif :</b> {_e(reason)}</p>" if reason else ""
    html_content = _layout(
        title="Votre boutique a été suspendue",
        intro=f"Bonjour {_e(owner_name)},",
        body_html=(
            f"<p>Votre boutique <b>{_e(shop_name)}</b> a été suspendue par l'administration.</p>"
            f"{reason_html}"
            "<p>L'accès de tous les comptes de la boutique est désactivé jusqu'à nouvel ordre. "
            "Contactez notre équipe pour plus d'informations.</p>"
        ),
    )
    send_email(owner_email, owner_name, "Votre boutique a été suspendue", html_content)


def send_shop_reactivated_email(owner_name: str, owner_email: str, shop_name: str) -> None:
    html_content = _layout(
        title="Votre boutique a été réactivée",
        intro=f"Bonjour {_e(owner_name)},",
        body_html=(
            f"<p>Bonne nouvelle : votre boutique <b>{_e(shop_name)}</b> a été réactivée.</p>"
            "<p>Vous et votre équipe pouvez de nouveau vous connecter avec vos identifiants habituels.</p>"
        ),
        button_label="Se connecter",
        button_url=f"{_frontend_url()}/login",
    )
    send_email(owner_email, owner_name, "Votre boutique a été réactivée", html_content)


def send_owner_password_reset_email(owner_name: str, owner_email: str, shop_name: str, temp_password: str) -> None:
    html_content = _layout(
        title="Réinitialisation de votre mot de passe",
        intro=f"Bonjour {_e(owner_name)},",
        body_html=(
            f"<p>Un nouveau mot de passe temporaire a été généré pour votre boutique <b>{_e(shop_name)}</b> "
            "à la demande de l'administration.</p>"
            f"{_credentials_box('Votre nouveau mot de passe', owner_email, temp_password)}"
            "<p>Pour votre sécurité, il vous sera demandé de choisir un nouveau mot de passe "
            "dès votre prochaine connexion.</p>"
        ),
        button_label="Se connecter maintenant",
        button_url=f"{_frontend_url()}/login",
    )
    send_email(owner_email, owner_name, "Votre mot de passe a été réinitialisé", html_content)


def send_password_reset_code_email(user_name: str, user_email: str, code: str, validity_minutes: int) -> None:
    # Ne jamais logger `code` : send_email ne logge que le destinataire.
    code_box = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="background-color:#f3f4f6; border-radius:8px; margin:16px 0;">
      <tr>
        <td align="center" style="padding:20px;">
          <p style="margin:0 0 8px 0; font-size:12px; color:#6b7280; text-transform:uppercase; letter-spacing:0.05em;">
            Votre code de vérification
          </p>
          <span style="font-family:monospace; font-size:28px; font-weight:bold; letter-spacing:0.3em; color:#111827;">{_e(code)}</span>
        </td>
      </tr>
    </table>
    """
    email_html = _layout(
        title="Réinitialisation de votre mot de passe",
        intro=f"Bonjour {_e(user_name)},",
        body_html=(
            "<p>Vous avez demandé à réinitialiser votre mot de passe. "
            "Saisissez le code ci-dessous dans l'application pour en choisir un nouveau.</p>"
            f"{code_box}"
            f"<p>Ce code est valable <b>{int(validity_minutes)} minutes</b> et ne peut être utilisé qu'une seule fois.</p>"
            "<p>Si vous n'êtes pas à l'origine de cette demande, ignorez ce message : "
            "votre mot de passe reste inchangé. Ne communiquez jamais ce code.</p>"
        ),
    )
    send_email(user_email, user_name, "Votre code de réinitialisation de mot de passe", email_html)


def send_shop_rejected_email(owner_name: str, owner_email: str, shop_name: str, reason: str | None = None) -> None:
    reason_html = f"<p><b>Motif :</b> {_e(reason)}</p>" if reason else ""
    html_content = _layout(
        title="Votre demande n'a pas été validée",
        intro=f"Bonjour {_e(owner_name)},",
        body_html=(
            f"<p>Nous sommes désolés de vous informer que votre demande pour la boutique "
            f"<b>{_e(shop_name)}</b> n'a pas été validée.</p>"
            f"{reason_html}"
            "<p>Vous pouvez nous contacter pour plus d'informations ou soumettre une nouvelle demande.</p>"
        ),
        button_label="Soumettre une nouvelle demande",
        button_url=f"{_frontend_url()}/register",
    )
    send_email(owner_email, owner_name, "Votre demande n'a pas été validée", html_content)
