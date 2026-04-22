# backend/celery.py
"""
Configuration Celery pour Restaurant Manager Pro.
Worker : traitement asynchrone des taches.
Beat   : planification des taches periodiques.

Demarrage en dev (Docker) :
  celery -A backend worker --loglevel=info
  celery -A backend beat   --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
"""
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')

# Lire la config depuis Django settings (namespace CELERY_)
app.config_from_object('django.conf:settings', namespace='CELERY')

# Decouverte automatique des taches dans chaque app
app.autodiscover_tasks()


# ── Planification des taches periodiques (Celery Beat) ────────────────────
app.conf.beat_schedule = {

    # Ouverture automatique de la Caisse Globale a 5h00
    # (heure Africa/Conakry — TIME_ZONE dans settings.py)
    'ouvrir-caisse-globale-5h00': {
        'task': 'apps.paiements.tasks.ouvrir_caisse_globale_quotidienne',
        'schedule': crontab(hour=5, minute=0),
        'options': {'expires': 3600},  # expire si non execute en 1h
    },

    # Phase 8 — rapport quotidien a 18h00
    # 'rapport-quotidien-18h00': {
    #     'task': 'apps.dashboard.tasks.envoyer_rapport_quotidien',
    #     'schedule': crontab(hour=18, minute=0),
    # },
}

app.conf.timezone = 'Africa/Conakry'


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')