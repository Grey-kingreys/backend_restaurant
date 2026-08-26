# apps/restaurant/services/email_service.py
"""
Emails transactionnels liés aux réservations (via Zendou).
Réutilise l'envoi bas niveau de apps.company.services.email_service.
"""

import logging
from apps.company.services.email_service import _send, render_email

logger = logging.getLogger(__name__)


def _fmt_date_fr(d):
    mois = ["", "janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    return f"{d.day} {mois[d.month]} {d.year}"


def _heure_fin(heure, duree_minutes):
    from datetime import datetime, date, timedelta
    fin = datetime.combine(date.min, heure) + timedelta(minutes=duree_minutes)
    return fin.strftime("%H:%M")


def _wrap(titre, contenu, restaurant_nom):
    return render_email(titre, contenu, footer_line=f"{restaurant_nom} - via resfly")


def send_reservation_client(resa) -> bool:
    """
    Confirmation envoyée AU CLIENT.
    NB : le numéro de table n'est volontairement PAS communiqué (le restaurant
    peut réaffecter la table le jour J).
    """
    client = resa.client
    if not client.email:
        return False

    auto = resa.statut == 'confirmee'
    statut_phrase = (
        "Votre réservation est <strong>confirmée</strong>."
        if auto else
        "Votre demande de réservation a bien été reçue. Le restaurant la confirmera sous peu."
    )
    contenu = f"""
        <p>Bonjour <strong>{client.nom_complet or client.login}</strong>,</p>
        <p>{statut_phrase}</p>
        <table style="margin:18px 0; font-size:15px;">
            <tr><td style="padding:4px 12px 4px 0; color:#718096;">Restaurant</td><td><strong>{resa.restaurant.nom}</strong></td></tr>
            <tr><td style="padding:4px 12px 4px 0; color:#718096;">Date</td><td>{_fmt_date_fr(resa.date_reservation)}</td></tr>
            <tr><td style="padding:4px 12px 4px 0; color:#718096;">Heure</td><td>{resa.heure.strftime('%H:%M')}</td></tr>
            <tr><td style="padding:4px 12px 4px 0; color:#718096;">Personnes</td><td>{resa.nombre_personnes}</td></tr>
        </table>
        <p style="color:#718096; font-size:14px;">Votre table vous sera indiquée à votre arrivée. Merci de prévenir le restaurant en cas d'empêchement.</p>
    """
    return _send(
        to=client.email,
        subject=f"Réservation chez {resa.restaurant.nom}",
        html_body=_wrap("Votre réservation", contenu, resa.restaurant.nom),
    )


def send_reservation_restaurant(resa) -> bool:
    """
    Notification envoyée AU RESTAURANT (email admin) - avec le numéro de table
    attribué (réaffectable depuis le tableau de bord).
    """
    resto = resa.restaurant
    if not resto.email_admin:
        return False

    no_show = resa.client_no_show_count if hasattr(resa, 'client_no_show_count') else None
    avert = ""
    if no_show and no_show >= 3:
        avert = f'<p style="color:#b91c1c; font-weight:bold;">⚠ Ce client a {no_show} absence(s) (no-show) enregistrée(s).</p>'

    table_no = resa.table.numero_table if resa.table_id else '-'
    contenu = f"""
        <p>Une nouvelle réservation vient d'être enregistrée.</p>
        {avert}
        <table style="margin:18px 0; font-size:15px;">
            <tr><td style="padding:4px 12px 4px 0; color:#718096;">Client</td><td><strong>{resa.client.nom_complet or resa.client.login}</strong></td></tr>
            <tr><td style="padding:4px 12px 4px 0; color:#718096;">Téléphone</td><td>{resa.client.telephone or '-'}</td></tr>
            <tr><td style="padding:4px 12px 4px 0; color:#718096;">Date</td><td>{_fmt_date_fr(resa.date_reservation)}</td></tr>
            <tr><td style="padding:4px 12px 4px 0; color:#718096;">Heure</td><td>{resa.heure.strftime('%H:%M')} → {_heure_fin(resa.heure, resa.duree_minutes)}</td></tr>
            <tr><td style="padding:4px 12px 4px 0; color:#718096;">Personnes</td><td>{resa.nombre_personnes}</td></tr>
            <tr><td style="padding:4px 12px 4px 0; color:#718096;">Table attribuée</td><td><strong>Table {table_no}</strong> (réaffectable)</td></tr>
            <tr><td style="padding:4px 12px 4px 0; color:#718096;">Statut</td><td>{resa.get_statut_display()}</td></tr>
        </table>
        {f'<p style="color:#718096; font-size:14px;">Note : « {resa.note} »</p>' if resa.note else ''}
    """
    return _send(
        to=resto.email_admin,
        subject=f"Nouvelle réservation - {resa.client.nom_complet or resa.client.login} ({resa.nombre_personnes} pers.)",
        html_body=_wrap("Nouvelle réservation", contenu, resto.nom),
    )
