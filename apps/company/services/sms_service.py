"""
Service d'envoi de SMS via Nimba SMS (opérateur guinéen).

Variables d'environnement :
- NIMBA_SMS_SID    : Service ID (clé API du dashboard Nimba)
- NIMBA_SMS_TOKEN  : Secret Token (jeton API)
- NIMBA_SMS_SENDER : nom d'expéditeur validé sur Nimba (défaut « RESFLY »)

Comportement dégradé volontaire : si les identifiants sont absents (dev) ou si
le SDK n'est pas installé, l'envoi devient un no-op loggé — jamais d'exception,
pour ne pas casser le parcours de commande.
"""

import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_client():
    """Retourne un client Nimba configuré, ou None si indisponible/non configuré."""
    sid = getattr(settings, 'NIMBA_SMS_SID', '')
    token = getattr(settings, 'NIMBA_SMS_TOKEN', '')
    if not sid or not token:
        return None
    try:
        from nimbasms import Client
    except ImportError:
        logger.warning("Package 'nimbasms' non installé — SMS désactivé.")
        return None
    return Client(sid, token)


def sms_actif() -> bool:
    """Le service SMS est-il configuré (clés présentes) ?"""
    return bool(getattr(settings, 'NIMBA_SMS_SID', '') and getattr(settings, 'NIMBA_SMS_TOKEN', ''))


def send_sms(to, message: str) -> bool:
    """
    Envoie un SMS à un ou plusieurs numéros via Nimba.
    `to` : str (un numéro) ou liste de numéros, au format +224XXXXXXXXX.
    Retourne True si l'envoi a réussi, False sinon (sans lever d'exception).
    """
    numbers = [to] if isinstance(to, str) else list(to)
    numbers = [n for n in (str(x).strip() for x in numbers) if n]
    if not numbers:
        return False

    client = _get_client()
    if client is None:
        # Dev / non configuré : on trace mais on ne bloque pas le parcours.
        logger.info("SMS non envoyé (Nimba non configuré) → %s : %s", numbers, message)
        return False

    sender = getattr(settings, 'NIMBA_SMS_SENDER', 'RESFLY')
    try:
        response = client.messages.create(to=numbers, sender_name=sender, message=message)
        if getattr(response, 'ok', False):
            return True
        logger.warning("Échec envoi SMS Nimba : %s", getattr(response, 'data', None))
        return False
    except Exception as exc:  # réseau, quota, sender non validé…
        logger.error("Erreur envoi SMS Nimba : %s", exc)
        return False


def lien_recu(commande) -> str:
    """URL publique de suivi / reçu d'une commande (page confirmation par clé)."""
    base = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
    slug = commande.restaurant.get_slug()
    return f"{base}/restaurant/{slug}/confirmation/{commande.cle_suivi}"


def send_recu_sms(commande) -> bool:
    """
    Envoie au client le lien de suivi / reçu de sa commande par SMS.
    Nécessite un téléphone client et une clé de suivi. Best-effort.
    """
    tel = (commande.client_telephone or "").strip()
    if not tel or not commande.cle_suivi:
        return False
    message = (
        f"resfly : votre commande #{commande.id} chez {commande.restaurant.nom} "
        f"est bien enregistree. Suivi & recu : {lien_recu(commande)}"
    )
    return send_sms(tel, message)
