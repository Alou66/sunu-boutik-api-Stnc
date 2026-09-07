import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

BREVO_URL = "https://api.brevo.com/v3/smtp/email"

BRAND_COLOR = "#2563eb"


def _layout(title: str, intro: str, body_html: str, button_label: str | None = None, button_url: str | None = None) -> str:
    button_html = ""
    if button_label and button_url:
        button_html = f"""
        <tr>
          <td align="center" style="padding: 28px 0 8px 0;">
            <a href="{button_url}"
               style="background-color:{BRAND_COLOR}; color:#ffffff; text-decoration:none;
                      font-family:Arial, Helvetica, sans-serif; font-size:15px; font-weight:bold;
                      padding:14px 32px; border-radius:8px; display:inline-block;">
              {button_label}
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
    if not settings.BREVO_API_KEY or not settings.BREVO_SENDER_EMAIL:
        logger.warning("Brevo non configuré, email non envoyé à %s", to_email)
        return

    payload = {
        "sender": {"name": settings.BREVO_SENDER_NAME, "email": settings.BREVO_SENDER_EMAIL},
        "to": [{"email": to_email, "name": to_name}],
        "subject": subject,
        "htmlContent": html_content,
    }
    headers = {
        "api-key": settings.BREVO_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        resp = httpx.post(BREVO_URL, json=payload, headers=headers, timeout=10)
        if resp.status_code >= 300:
            logger.error("Echec envoi email Brevo (%s): %s", resp.status_code, resp.text)
    except httpx.HTTPError as exc:
        logger.error("Erreur réseau lors de l'envoi de l'email: %s", exc)


def send_signup_pending_emails(
    shop_name: str, owner_name: str, owner_email: str, frontend_url: str | None = None
) -> None:
    base_url = frontend_url or settings.FRONTEND_URL
    login_url = f"{base_url}/login"
    client_html = _layout(
        title="Votre demande est en cours de traitement",
        intro=f"Bonjour {owner_name},",
        body_html=(
            f"<p>Votre demande de création de la boutique <b>{shop_name}</b> a bien été reçue.</p>"
            "<p>Elle est actuellement <b>en cours de traitement</b> par notre équipe. "
            "Vous recevrez un email dès que votre compte sera validé. "
            "Vous ne pourrez pas vous connecter avant cette validation.</p>"
        ),
        button_label="Accéder à la page de connexion",
        button_url=login_url,
    )
    send_email(owner_email, owner_name, "Votre demande est en cours de traitement", client_html)

    if settings.ADMIN_EMAIL:
        admin_url = f"{base_url}/admin/login"
        admin_html = _layout(
            title="Nouvelle demande de boutique à valider",
            intro="Une nouvelle boutique attend votre validation.",
            body_html=(
                "<table role='presentation' width='100%' cellpadding='6' cellspacing='0' style='font-size:14px;'>"
                f"<tr><td style='color:#6b7280;'>Boutique</td><td style='font-weight:bold;'>{shop_name}</td></tr>"
                f"<tr><td style='color:#6b7280;'>Propriétaire</td><td style='font-weight:bold;'>{owner_name}</td></tr>"
                f"<tr><td style='color:#6b7280;'>Email</td><td style='font-weight:bold;'>{owner_email}</td></tr>"
                "</table>"
            ),
            button_label="Ouvrir le dashboard admin",
            button_url=admin_url,
        )
        send_email(settings.ADMIN_EMAIL, "Admin", "Nouvelle demande de boutique à valider", admin_html)


def send_shop_approved_email(
    owner_name: str,
    owner_email: str,
    shop_name: str,
    temp_password: str,
    frontend_url: str | None = None,
) -> None:
    login_url = f"{frontend_url or settings.FRONTEND_URL}/login"
    credentials_box = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="background-color:#f3f4f6; border-radius:8px; margin:16px 0;">
      <tr>
        <td style="padding:16px 20px;">
          <p style="margin:0 0 8px 0; font-size:12px; color:#6b7280; text-transform:uppercase; letter-spacing:0.05em;">
            Vos identifiants de connexion
          </p>
          <p style="margin:0 0 4px 0; font-size:14px; color:#111827;">
            <b>Email :</b> {owner_email}
          </p>
          <p style="margin:0; font-size:14px; color:#111827;">
            <b>Mot de passe temporaire :</b>
            <span style="font-family:monospace; background-color:#fff; border:1px solid #e5e7eb; padding:2px 8px; border-radius:4px;">{temp_password}</span>
          </p>
        </td>
      </tr>
    </table>
    """
    html = _layout(
        title="Votre boutique a été validée 🎉",
        intro=f"Bonjour {owner_name},",
        body_html=(
            f"<p>Bonne nouvelle ! Votre boutique <b>{shop_name}</b> a été validée.</p>"
            f"{credentials_box}"
            "<p>Pour votre sécurité, il vous sera demandé de choisir un nouveau mot de passe "
            "dès votre première connexion.</p>"
        ),
        button_label="Se connecter maintenant",
        button_url=login_url,
    )
    send_email(owner_email, owner_name, "Votre boutique a été validée", html)


def send_shop_rejected_email(
    owner_name: str,
    owner_email: str,
    shop_name: str,
    reason: str | None = None,
    frontend_url: str | None = None,
) -> None:
    register_url = f"{frontend_url or settings.FRONTEND_URL}/register"
    reason_html = f"<p><b>Motif :</b> {reason}</p>" if reason else ""
    html = _layout(
        title="Votre demande n'a pas été validée",
        intro=f"Bonjour {owner_name},",
        body_html=(
            f"<p>Nous sommes désolés de vous informer que votre demande pour la boutique "
            f"<b>{shop_name}</b> n'a pas été validée.</p>"
            f"{reason_html}"
            "<p>Vous pouvez nous contacter pour plus d'informations ou soumettre une nouvelle demande.</p>"
        ),
        button_label="Soumettre une nouvelle demande",
        button_url=register_url,
    )
    send_email(owner_email, owner_name, "Votre demande n'a pas été validée", html)
