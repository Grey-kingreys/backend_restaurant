"""Backfill : cree la Caisse Generale manquante des restaurants existants.

Seuls le seed de demo et `/caisse-generale/init/` creaient une CaisseGenerale.
Les restaurants nes de l'onboarding n'en avaient donc aucune, et chaque
transfert d'argent (validation d'approvisionnement, fermeture de caisse
globale / comptable) levait `RelatedObjectDoesNotExist` -> HTTP 500.
"""
from decimal import Decimal

from django.db import migrations


def creer_caisses_generales_manquantes(apps, schema_editor):
    Restaurant = apps.get_model('company', 'Restaurant')
    CaisseGenerale = apps.get_model('paiements', 'CaisseGenerale')

    sans_coffre = Restaurant.objects.filter(caisse_generale__isnull=True)
    CaisseGenerale.objects.bulk_create([
        CaisseGenerale(
            restaurant=restaurant,
            solde=Decimal('0.00'),
            solde_initial=Decimal('0.00'),
        )
        for restaurant in sans_coffre
    ])


def noop(apps, schema_editor):
    """Irreversible : on ne supprime pas un coffre qui peut deja contenir de l'argent."""


class Migration(migrations.Migration):

    dependencies = [
        ('paiements', '0003_demandeapprovisionnement'),
        ('company', '0006_restaurant_livraison_lien_autorise_paiement'),
    ]

    operations = [
        migrations.RunPython(creer_caisses_generales_manquantes, noop),
    ]
