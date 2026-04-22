# backend/__init__.py
# Charge l'app Celery au demarrage de Django
# afin que les taches @shared_task soient enregistrees.
from .celery import app as celery_app

__all__ = ('celery_app',)