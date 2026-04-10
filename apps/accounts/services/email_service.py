# apps/accounts/services/email_service.py
import logging
import resend
from django.conf import settings

logger = logging.getLogger(__name__)


def send_password_reset_email(user, reset_token) -> bool:
    """
    Envoie un email de réinitialisation de mot de passe.
    Le lien redirige vers le frontend React.
    Retourne True si l'envoi a réussi, False sinon.
    """
    reset_url = f"{settings.FRONTEND_URL}/auth/reset-password?token={reset_token.token}"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #2d3748;">Réinitialisation de votre mot de passe</h2>
        <p>Bonjour <strong>{user.nom_complet or user.login}</strong>,</p>
        <p>Vous avez demandé la réinitialisation de votre mot de passe sur <strong>Restaurant Manager Pro</strong>.</p>
        <p>Cliquez sur le bouton ci-dessous pour définir un nouveau mot de passe :</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}"
               style="background-color: #4f46e5; color: white; padding: 14px 28px;
                      text-decoration: none; border-radius: 6px; font-size: 16px;">
                Réinitialiser mon mot de passe
            </a>
        </div>
        <p style="color: #718096; font-size: 14px;">
            Ce lien est valable <strong>1 heure</strong> et ne peut être utilisé qu'une seule fois.
        </p>
        <p style="color: #718096; font-size: 14px;">
            Si vous n'avez pas fait cette demande, ignorez cet email — votre mot de passe reste inchangé.
        </p>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
        <p style="color: #a0aec0; font-size: 12px; text-align: center;">
            Restaurant Manager Pro — {user.restaurant.nom if user.restaurant else 'Plateforme'}
        </p>
    </body>
    </html>
    """

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