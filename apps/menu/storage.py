# apps/menu/storage.py
"""
Backend de stockage conditionnel.
- En développement (USE_S3=False ou absent) : stockage local Django par défaut.
- En production (USE_S3=True)               : AWS S3 via django-storages.

Variables d'environnement requises pour S3 :
    USE_S3=True
    AWS_ACCESS_KEY_ID=...
    AWS_SECRET_ACCESS_KEY=...
    AWS_STORAGE_BUCKET_NAME=...
    AWS_S3_REGION_NAME=eu-west-1   (optionnel, défaut us-east-1)
    AWS_S3_CUSTOM_DOMAIN=...       (optionnel — CDN / CloudFront)

Usage dans settings.py :
    from apps.menu.storage import get_image_storage
    DEFAULT_FILE_STORAGE = get_image_storage()
"""

import os


def get_image_storage():
    """
    Retourne la classe de stockage à utiliser selon USE_S3.
    Appelée dans settings.py.
    """
    if os.getenv('USE_S3', 'False').lower() == 'true':
        return 'storages.backends.s3boto3.S3Boto3Storage'
    # Stockage local Django par défaut (media/)
    return 'django.core.files.storage.FileSystemStorage'


def get_s3_settings():
    """
    Retourne un dict de settings S3 à injecter dans Django settings.
    Ne pas appeler si USE_S3=False.
    """
    bucket = os.getenv('AWS_STORAGE_BUCKET_NAME', '')
    region = os.getenv('AWS_S3_REGION_NAME', 'us-east-1')
    custom_domain = os.getenv('AWS_S3_CUSTOM_DOMAIN', '')

    settings = {
        'AWS_ACCESS_KEY_ID': os.getenv('AWS_ACCESS_KEY_ID', ''),
        'AWS_SECRET_ACCESS_KEY': os.getenv('AWS_SECRET_ACCESS_KEY', ''),
        'AWS_STORAGE_BUCKET_NAME': bucket,
        'AWS_S3_REGION_NAME': region,
        # Pas de query string auth — URLs publiques pour les images
        'AWS_QUERYSTRING_AUTH': False,
        # Cache-Control pour les images (1 an)
        'AWS_S3_OBJECT_PARAMETERS': {
            'CacheControl': 'max-age=31536000',
        },
        # Sous-dossier dans le bucket
        'AWS_LOCATION': os.getenv('AWS_S3_LOCATION', 'media'),
    }

    if custom_domain:
        settings['AWS_S3_CUSTOM_DOMAIN'] = custom_domain
        settings['MEDIA_URL'] = f'https://{custom_domain}/media/'
    else:
        settings['MEDIA_URL'] = (
            f'https://{bucket}.s3.{region}.amazonaws.com/media/'
        )

    return settings