# apps/paiements/tasks.py
"""
Taches Celery pour la gestion automatique des caisses.
- ouvrir_caisse_globale_quotidienne : s'execute a 5h00 chaque matin
  via Celery Beat (configure dans backend/celery.py).
"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def ouvrir_caisse_globale_quotidienne(self):
    """
    Ouvre automatiquement la Caisse Globale du jour pour chaque restaurant actif
    qui n'en a pas encore une ouverte.
    Planifie a 5h00 (heure de Conakry, Africa/Conakry) via Celery Beat.
    """
    from apps.company.models import Restaurant
    from apps.paiements.models import CaisseGlobale

    today = timezone.localdate()
    restaurants_actifs = Restaurant.objects.filter(is_active=True)

    ouverts  = 0
    ignores  = 0
    erreurs  = 0

    for restaurant in restaurants_actifs:
        try:
            # Verifier si une caisse existe deja pour aujourd'hui
            deja = CaisseGlobale.objects.filter(
                restaurant=restaurant,
                date_ouverture=today,
            ).exists()

            if deja:
                ignores += 1
                continue

            CaisseGlobale.objects.create(
                restaurant=restaurant,
                date_ouverture=today,
            )
            ouverts += 1
            logger.info(
                "[CaisseGlobale] Ouverte pour %s le %s",
                restaurant.nom, today,
            )

        except Exception as exc:
            erreurs += 1
            logger.error(
                "[CaisseGlobale] Erreur pour %s : %s",
                restaurant.nom, exc,
            )

    logger.info(
        "[CaisseGlobale] Bilan %s : %d ouvertes, %d ignorees, %d erreurs",
        today, ouverts, ignores, erreurs,
    )
    return {
        'date': str(today),
        'ouverts': ouverts,
        'ignores': ignores,
        'erreurs': erreurs,
    }


@shared_task(bind=True, max_retries=2)
def creer_remise_pour_paiement(self, paiement_id):
    """
    Cree une RemiseServeur en attente pour un paiement PAYEE.
    Appelee depuis apps/commandes/serializers.py lors du passage PAYEE.
    Rattache la remise a la Caisse Globale active du restaurant.
    """
    from apps.paiements.models import Paiement, CaisseGlobale, RemiseServeur

    try:
        paiement = Paiement.objects.select_related(
            'commande__restaurant',
            'commande__serveur_ayant_servi',
        ).get(pk=paiement_id)
    except Paiement.DoesNotExist:
        logger.error("[RemiseServeur] Paiement %d introuvable", paiement_id)
        return

    # Eviter les doublons
    if hasattr(paiement, 'remise'):
        logger.warning(
            "[RemiseServeur] RemiseServeur deja existante pour paiement %d",
            paiement_id,
        )
        return

    restaurant = paiement.commande.restaurant
    caisse_globale = CaisseGlobale.objects.filter(
        restaurant=restaurant, is_closed=False
    ).first()

    if not caisse_globale:
        logger.warning(
            "[RemiseServeur] Aucune Caisse Globale active pour %s "
            "— paiement %d sans remise",
            restaurant.nom, paiement_id,
        )
        return

    serveur = paiement.commande.serveur_ayant_servi
    RemiseServeur.objects.create(
        caisse_globale=caisse_globale,
        paiement=paiement,
        serveur=serveur,
        montant_virtuel=paiement.montant,
    )
    logger.info(
        "[RemiseServeur] Creee pour paiement %d — serveur %s — montant %s GNF",
        paiement_id,
        serveur.login if serveur else "inconnu",
        paiement.montant,
    )
