import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')

# ------------------------------------------
# SECURITE
# ------------------------------------------
SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# ------------------------------------------
# APPLICATIONS
# ------------------------------------------
USE_S3 = os.getenv('USE_S3', 'False').lower() == 'true'
 
INSTALLED_APPS = [
    'django_prometheus',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # DRF
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',
 
    # Storage S3 — chargé uniquement si USE_S3=True
    *(['storages'] if USE_S3 else []),
 
    'apps.company',
    'apps.accounts',
    'apps.menu',
    'apps.commandes',
    'apps.restaurant',
    'apps.paiements',
    'apps.dashboard',
]

AUTH_USER_MODEL = 'accounts.User'


# ------------------------------------------
# SWAGGER / OpenAPI — drf-spectacular
# ------------------------------------------
SPECTACULAR_SETTINGS = {
    'TITLE': 'Restaurant Manager API',
    'DESCRIPTION': 'API SaaS multi-tenant pour la gestion de restaurants.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
}

# ------------------------------------------
# MIDDLEWARE
# ------------------------------------------
MIDDLEWARE = [
    'django_prometheus.middleware.PrometheusBeforeMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_prometheus.middleware.PrometheusAfterMiddleware',
    # 'apps.restaurant.middleware.AutoLogoutTableMiddleware', # Phase 6
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

# ------------------------------------------
# BASE DE DONNEES
# SQLite si pas de DB_NAME dans .env
# PostgreSQL si DB_NAME defini
# ------------------------------------------
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

FIXTURE_DIRS = [
    BASE_DIR / 'fixtures',
]

# ------------------------------------------
# DJANGO REST FRAMEWORK
# ------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'apps.accounts.exceptions.custom_exception_handler',
}

# ------------------------------------------
# JWT - SimpleJWT
# ------------------------------------------
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(
        minutes=int(os.getenv('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', 60))
    ),
    'REFRESH_TOKEN_LIFETIME': timedelta(
        days=int(os.getenv('JWT_REFRESH_TOKEN_LIFETIME_DAYS', 7))
    ),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    # 'TOKEN_OBTAIN_SERIALIZER': 'apps.accounts.serializers.CustomTokenObtainPairSerializer',
}

# ------------------------------------------
# CORS
# ------------------------------------------
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
]
CORS_ALLOW_CREDENTIALS = True

# ------------------------------------------
# INTERNATIONALISATION
# ------------------------------------------
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Conakry'
USE_I18N = True
USE_TZ = True

# ------------------------------------------
# FICHIERS STATIQUES ET MEDIA
# ------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
if USE_S3:
    AWS_ACCESS_KEY_ID      = os.getenv('AWS_ACCESS_KEY_ID', '')
    AWS_SECRET_ACCESS_KEY  = os.getenv('AWS_SECRET_ACCESS_KEY', '')
    AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME', '')
    AWS_S3_REGION_NAME     = os.getenv('AWS_S3_REGION_NAME', 'us-east-1')
    AWS_S3_LOCATION        = os.getenv('AWS_S3_LOCATION', 'media')
    AWS_QUERYSTRING_AUTH   = False
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=31536000'}
 
    _cdn = os.getenv('AWS_S3_CUSTOM_DOMAIN', '')
    if _cdn:
        AWS_S3_CUSTOM_DOMAIN = _cdn
        MEDIA_URL = f'https://{_cdn}/{AWS_S3_LOCATION}/'
    else:
        MEDIA_URL = (
            f'https://{AWS_STORAGE_BUCKET_NAME}'
            f'.s3.{AWS_S3_REGION_NAME}.amazonaws.com/{AWS_S3_LOCATION}/'
        )
 
    MEDIA_ROOT = ''
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
 
else:
    # Développement — stockage local (inchangé)
    MEDIA_URL  = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
 

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ------------------------------------------
# SESSIONS
# ------------------------------------------
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 86400

# ------------------------------------------
# VALIDATION MOTS DE PASSE
# ------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ------------------------------------------
# EMAIL
# ------------------------------------------
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ------------------------------------------
# RESEND
# ------------------------------------------
RESEND_KEY = os.getenv('RESEND_KEY', '')
RESEND_FROM_EMAIL = os.getenv('RESEND_FROM_EMAIL', 'noreply@kingreys.fr')
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')