"""Tâches Celery de l'app publique."""
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import CleIdempotence

DUREE_CONSERVATION_CLES = timedelta(hours=24)


@shared_task
def purger_cles_idempotence():
    """Supprime les clés d'idempotence de plus de 24 h. Planifiée dans backend/celery.py."""
    supprimees, _ = CleIdempotence.objects.filter(
        date_creation__lt=timezone.now() - DUREE_CONSERVATION_CLES,
    ).delete()
    return supprimees
