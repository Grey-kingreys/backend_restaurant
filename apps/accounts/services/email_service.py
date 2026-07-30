# apps/accounts/services/email_service.py
import logging
import resend
from django.conf import settings
from apps.company.services.email_service import render_email, email_button

logger = logging.getLogger(__name__)


def send_password_reset_email(user, reset_token) -> bool:
    """
    Envoie un email de réinitialisation de mot de passe.
    Le lien redirige vers le frontend React.
    Retourne True si l'envoi a réussi, False sinon.
    """
    reset_url = f"{settings.FRONTEND_URL}/auth/reset-password?token={reset_token.token}"

    body = f"""
        <p style="margin:0 0 12px;">Bonjour <strong>{user.nom_complet or user.login}</strong>,</p>
        <p style="margin:0 0 4px;">
          Vous avez demandé la réinitialisation de votre mot de passe sur <strong>resfly</strong>.
          Cliquez sur le bouton ci-dessous pour en définir un nouveau :
        </p>
        {email_button("Réinitialiser mon mot de passe", reset_url)}
        <p style="color:#78716c; font-size:14px; margin:0 0 8px;">
          Ce lien est valable <strong>1 heure</strong> et ne peut être utilisé qu'une seule fois.
        </p>
        <p style="color:#78716c; font-size:14px; margin:0;">
          Si vous n'avez pas fait cette demande, ignorez cet email — votre mot de passe reste inchangé.
        </p>
    """

    html_content = render_email(
        "Réinitialisation de votre mot de passe",
        body,
        footer_line=f"resfly — {user.restaurant.nom if user.restaurant else 'Plateforme'}",
    )

    if not settings.RESEND_KEY:
        # Pas de clé configurée (dev sans email, tests) → no-op silencieux.
        logger.info("[PasswordReset] RESEND_KEY absent — email non envoyé (no-op).")
        return False

    try:
        resend.api_key = settings.RESEND_KEY
        resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": [user.email],
            "subject": "Réinitialisation de votre mot de passe",
            "html": html_content,
        })
        logger.info(f"[PasswordReset] Email envoyé à {user.email}")
        return True
    except Exception as e:
        logger.error(f"[PasswordReset] Échec envoi email à {user.email} : {e}")
        return False