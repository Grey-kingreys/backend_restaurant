# apps/company/services/email_service.py
"""
Service d'envoi d'email via Resend.
Variable d'environnement requise : RESEND_KEY
Domaine expediteur : kingreys.fr (verifie sur Resend)
"""

import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def _send(to: str, subject: str, html_body: str) -> bool:
    """
    Fonction interne — envoie un email via l'API Resend.
    Retourne True si succes, False si echec (sans lever d'exception).
    """
    payload = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to],
        "subject": subject,
        "html": html_body,
    }
    headers = {
        "Authorization": f"Bearer {settings.RESEND_KEY}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(
            RESEND_API_URL,
            json=payload,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"[Email] Envoye a {to} — sujet: {subject}")
        return True
    except Exception as exc:
        logger.error(f"[Email] Echec envoi a {to}: {exc}")
        return False


def send_welcome_email(admin_user, restaurant, onboarding_token) -> bool:
    """
    Envoie l'email de bienvenue a l'Admin nouvellement cree par le Super Admin.

    Args:
        admin_user    : instance User (role=Radmin)
        restaurant    : instance Restaurant
        onboarding_token : instance OnboardingToken

    L'email contient :
    - Le nom du restaurant
    - Le login de l'Admin
    - Un lien de premiere connexion valable 48h
    """
    frontend_url = settings.FRONTEND_URL.rstrip("/")
    first_login_link = (
        f"{frontend_url}/auth/first-login?token={onboarding_token.token}"
    )

    html_body = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;
                 padding: 20px; color: #333; background: #f9f9f9;">

      <div style="background: #fff; border-radius: 12px; padding: 32px;
                  box-shadow: 0 2px 8px rgba(0,0,0,0.07);">

        <h2 style="color: #1a1a2e; margin-bottom: 4px;">
          Bienvenue sur Restaurant Manager Pro
        </h2>
        <p style="color: #666; font-size: 13px; margin-top: 0;">
          Votre restaurant a ete cree avec succes sur la plateforme.
        </p>

        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">

        <p>Bonjour,</p>
        <p>
          Le restaurant <strong>{restaurant.nom}</strong> vient d'etre enregistre
          sur <strong>Restaurant Manager Pro</strong>.
          Vous etes designe(e) comme administrateur(trice) de ce restaurant.
        </p>

        <div style="background: #f4f4f8; border-radius: 8px; padding: 16px; margin: 20px 0;">
          <p style="margin: 0 0 6px; font-size: 13px; color: #888;">
            Vos informations de connexion
          </p>
          <p style="margin: 0; font-size: 15px;">
            <strong>Login :</strong>
            <code style="background: #e8e8f0; padding: 2px 8px; border-radius: 4px;">
              {admin_user.login}
            </code>
          </p>
        </div>

        <p>
          Cliquez sur le bouton ci-dessous pour definir votre mot de passe
          et acceder a votre espace. Ce lien est valable <strong>48 heures</strong>.
        </p>

        <div style="text-align: center; margin: 32px 0;">
          <a href="{first_login_link}"
             style="background-color: #f0883e; color: white; padding: 14px 32px;
                    text-decoration: none; border-radius: 8px; font-weight: bold;
                    display: inline-block; font-size: 15px;">
            Acceder a mon espace →
          </a>
        </div>

        <p style="color: #666; font-size: 13px;">
          Si le bouton ne fonctionne pas, copiez ce lien dans votre navigateur :<br>
          <a href="{first_login_link}" style="color: #f0883e; word-break: break-all;">
            {first_login_link}
          </a>
        </p>

        <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">

        <p style="color: #999; font-size: 12px; margin: 0;">
          Si vous n'etes pas concerne(e) par cet email, ignorez-le.<br>
          Ce lien expirera automatiquement dans 48 heures.<br>
          &copy; {restaurant.created_at.year} Restaurant Manager Pro — Conakry, Guinee
        </p>

      </div>
    </body>
    </html>
    """

    return _send(
        to=admin_user.email,
        subject=f"Bienvenue sur Restaurant Manager Pro — {restaurant.nom}",
        html_body=html_body,
    )