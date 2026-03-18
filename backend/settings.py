import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')

# ──────────────────────────────────────────
# SÉCURITÉ
# ──────────────────────────────────────────
SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# ──────────────────────────────────────────
# APPLICATIONS
# ──────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # DRF
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',  # Pour le logout JWT
    'corsheaders',

    # Apps métier
    'apps.accounts',
    'apps.menu',
    'apps.commandes',
    'apps.restaurant',
    'apps.paiements',
    'apps.dashboard',
]

AUTH_USER_MODEL = 'accounts.User'

# ──────────────────────────────────────────
# MIDDLEWARE
# ──────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',          # CORS — doit être en haut
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # AutoLogoutTableMiddleware ajouté en Phase 6
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

# ──────────────────────────────────────────
# BASE DE DONNÉES
# SQLite en dev, PostgreSQL en prod
# ──────────────────────────────────────────
if os.getenv('DB_NAME'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME'),
            'USER': os.getenv('DB_USER'),
            'PASSWORD': os.getenv('DB_PASSWORD'),
            'HOST': os.getenv('DB_HOST'),
            'PORT': os.getenv('DB_PORT', '5432'),
            'OPTIONS': {
                'sslmode': os.getenv('DB_SSLMODE', 'require'),
                'connect_timeout': 10,
            },
            'CONN_MAX_AGE': 300,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ──────────────────────────────────────────
# DJANGO REST FRAMEWORK
# ──────────────────────────────────────────
REST_FRAMEWORK = {
    # JWT par défaut sur tous les endpoints
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    # Authentification requise par défaut
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    # Format réponse uniforme via un renderer custom (créé en Phase 3)
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    # Pagination globale : 20 items par page
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    # Gestion des exceptions custom (créée en Phase 3)
    'EXCEPTION_HANDLER': 'apps.accounts.exceptions.custom_exception_handler',
}

# ──────────────────────────────────────────
# JWT — SimpleJWT
# ──────────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(
        minutes=int(os.getenv('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', 60))
    ),
    'REFRESH_TOKEN_LIFETIME': timedelta(
        days=int(os.getenv('JWT_REFRESH_TOKEN_LIFETIME_DAYS', 7))
    ),
    'ROTATE_REFRESH_TOKENS': True,        # Nouveau refresh token à chaque refresh
    'BLACKLIST_AFTER_ROTATION': True,     # Ancien token blacklisté → logout propre
    'UPDATE_LAST_LOGIN': True,

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',

    # Champ utilisé comme identifiant dans le token
    # USERNAME_FIELD = 'login' → on override ici
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',

    'TOKEN_OBTAIN_SERIALIZER': 'apps.accounts.serializers.CustomTokenObtainPairSerializer',
}

# ──────────────────────────────────────────
# CORS — Cross-Origin Resource Sharing
# ──────────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
]
CORS_ALLOW_CREDENTIALS = True   # Nécessaire pour Flutter / mobile avec cookies

# ──────────────────────────────────────────
# INTERNATIONALISATION
# ──────────────────────────────────────────
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Conakry'
USE_I18N = True
USE_TZ = True

# ──────────────────────────────────────────
# FICHIERS STATIQUES ET MEDIA
# ──────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ──────────────────────────────────────────
# SESSIONS (pour le panier — rediscuté Phase 5)
# ──────────────────────────────────────────
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 86400  # 24h

# ──────────────────────────────────────────
# VALIDATION MOTS DE PASSE
# ──────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ──────────────────────────────────────────
# EMAIL (activé en Phase 8 avec Celery)
# ──────────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # Console en dev
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)
REPORT_EMAIL_TO = os.getenv('REPORT_EMAIL_TO', DEFAULT_FROM_EMAIL)