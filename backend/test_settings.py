"""
Test settings — Configuration Django optimisée pour pytest

Import depuis settings.py et override les valeurs pour les tests.
"""
from .settings import *

# Désactiver ATOMIC_REQUESTS en test pour meilleures perfs
DATABASES['default']['ATOMIC_REQUESTS'] = False
DATABASES['default']['CONN_MAX_AGE'] = 0

# Hash passwords plus rapidement en test (JAMAIS en prod!)
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Désactiver Celery — exécuter les tâches immédiatement
CELERY_ALWAYS_EAGER = True
CELERY_EAGER_PROPAGATES_EXCEPTIONS = True

# Silence les logs en test
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'null': {
            'class': 'logging.NullHandler',
        },
    },
    'root': {
        'handlers': ['null'],
    },
}
