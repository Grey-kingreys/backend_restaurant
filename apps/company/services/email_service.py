# apps/company/services/email_service.py
"""
Service d'envoi d'email via Resend.
Variable d'environnement requise : RESEND_KEY
Domaine expediteur : kingreys.fr (verifie sur Resend)
"""

import logging
import requests
from django.conf import settings
from django.utils.html import escape

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def _send(to: str, subject: str, html_body: str, reply_to: str | None = None) -> bool:
    """
    Fonction interne — envoie un email via l'API Resend.
    Retourne True si succes, False si echec (sans lever d'exception).
    `reply_to` (optionnel) : adresse à laquelle les réponses seront adressées.
    """
    if not settings.RESEND_KEY:
        # Pas de clé configurée (dev sans email, tests) → no-op sans appel réseau.
        logger.info(f"[Email] RESEND_KEY absent — email a {to} non envoye (no-op).")
        return False

    payload = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to],
        "subject": subject,
        "html": html_body,
    }
    if reply_to:
        payload["reply_to"] = reply_to
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


# ── Gabarit d'email brandé resfly ────────────────────────────────────────────
# Un seul habillage (logo + couleurs) réutilisé par tous les emails transactionnels.

def render_email(title: str, body_html: str, footer_line: str = "resfly — Conakry, Guinée") -> str:
    """Enveloppe HTML brandée resfly. `body_html` = contenu déjà en HTML.

    Le logo est rendu en TEXTE (wordmark « resfly ») et non en image : une image
    distante nécessiterait une URL publique (indisponible en dev → image cassée
    chez le destinataire) et le base64 est bloqué par Gmail. Le wordmark s'affiche
    partout, sans dépendance externe. Ajouter l'icône PNG le jour où un domaine
    public héberge le logo (ou via une pièce jointe inline CID).
    """
    return f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0; padding:0; background:#f5f5f4; font-family: Arial, Helvetica, sans-serif; color:#2d3748;">
  <div style="max-width:600px; margin:0 auto; padding:24px 16px;">
    <div style="text-align:center; padding:4px 0 22px;">
      <span style="font-size:28px; font-weight:800; letter-spacing:-0.5px;"><span style="color:#1c1917;">res</span><span style="color:#f59e0b;">fly</span></span>
    </div>
    <div style="background:#ffffff; border:1px solid #e7e5e4; border-radius:14px; padding:32px;">
      <h1 style="margin:0 0 18px; font-size:20px; color:#1c1917;">{title}</h1>
      {body_html}
    </div>
    <p style="color:#a8a29e; font-size:12px; text-align:center; margin:20px 0 0;">{footer_line}</p>
  </div>
</body>
</html>"""


def email_button(label: str, url: str) -> str:
    """Bouton d'action ambré (solide + dégradé si supporté)."""
    return (
        f'<div style="text-align:center; margin:28px 0;">'
        f'<a href="{url}" style="background-color:#f59e0b; background:linear-gradient(135deg,#f59e0b,#d97706); '
        f'color:#ffffff; padding:13px 30px; text-decoration:none; border-radius:10px; '
        f'font-weight:bold; font-size:15px; display:inline-block;">{label}</a></div>'
    )


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

    body = f"""
        <p style="color:#57534e; font-size:13px; margin:0 0 18px;">
          Votre restaurant a été créé avec succès sur la plateforme.
        </p>
        <p style="margin:0 0 12px;">Bonjour,</p>
        <p style="margin:0 0 12px;">
          Le restaurant <strong>{restaurant.nom}</strong> vient d'être enregistré sur
          <strong>resfly</strong>. Vous êtes désigné(e) comme administrateur(trice) de ce restaurant.
        </p>
        <div style="background:#f5f5f4; border:1px solid #e7e5e4; border-radius:10px; padding:16px; margin:20px 0;">
          <p style="margin:0 0 6px; font-size:13px; color:#a8a29e;">Vos informations de connexion</p>
          <p style="margin:0; font-size:15px;">
            <strong>Login :</strong>
            <code style="background:#e7e5e4; padding:2px 8px; border-radius:4px;">{admin_user.login}</code>
          </p>
        </div>
        <p style="margin:0 0 4px;">
          Cliquez sur le bouton ci-dessous pour définir votre mot de passe et accéder à votre
          espace. Ce lien est valable <strong>48 heures</strong>.
        </p>
        {email_button("Accéder à mon espace →", first_login_link)}
        <p style="color:#78716c; font-size:13px; margin:0;">
          Si le bouton ne fonctionne pas, copiez ce lien dans votre navigateur :<br>
          <a href="{first_login_link}" style="color:#d97706; word-break:break-all;">{first_login_link}</a>
        </p>
        <hr style="border:none; border-top:1px solid #e7e5e4; margin:24px 0;">
        <p style="color:#a8a29e; font-size:12px; margin:0;">
          Si vous n'êtes pas concerné(e) par cet email, ignorez-le.<br>
          Ce lien expirera automatiquement dans 48 heures.
        </p>
    """

    html_body = render_email(
        "Bienvenue sur resfly",
        body,
        footer_line=f"resfly — Conakry, Guinée · © {restaurant.created_at.year}",
    )

    return _send(
        to=admin_user.email,
        subject=f"Bienvenue sur resfly — {restaurant.nom}",
        html_body=html_body,
    )


def send_contact_message(nom: str, email: str, message: str) -> bool:
    """
    Envoie à l'équipe (settings.CONTACT_EMAIL) un message du formulaire de contact
    de la vitrine. `reply_to` = email du visiteur pour répondre directement.
    Les entrées utilisateur sont échappées (email HTML).
    """
    nom_s = escape(nom)
    email_s = escape(email)
    message_html = escape(message).replace("\n", "<br>")

    html_body = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color:#2d3748;">
        <h2 style="color:#b45309;">Nouveau message de contact</h2>
        <table style="margin:18px 0; font-size:15px;">
            <tr><td style="padding:4px 12px 4px 0; color:#718096;">Nom</td><td><strong>{nom_s}</strong></td></tr>
            <tr><td style="padding:4px 12px 4px 0; color:#718096;">Email</td><td><a href="mailto:{email_s}">{email_s}</a></td></tr>
        </table>
        <div style="background:#f7fafc; border-radius:8px; padding:16px; font-size:15px; line-height:1.5;">
            {message_html}
        </div>
        <hr style="border:none; border-top:1px solid #e2e8f0; margin:28px 0;">
        <p style="color:#a0aec0; font-size:12px; text-align:center;">
            Envoyé depuis le formulaire de contact — resfly
        </p>
    </body>
    </html>
    """

    return _send(
        to=settings.CONTACT_EMAIL,
        subject=f"Contact resfly — {nom_s}",
        html_body=html_body,
        reply_to=email if email else None,
    )