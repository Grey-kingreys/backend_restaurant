# Dockerfile - Restaurant Manager Pro (backend DRF)
# Multi-stage : builder -> runner

# Stage 1 - Builder
# Installation des dependances Python
FROM python:3.11-slim AS builder

WORKDIR /app

# Dependances systeme pour psycopg + Pillow + reportlab
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt


# Stage 2 - Runner (image finale legere)
FROM python:3.11-slim

WORKDIR /app

# Dependances systeme runtime uniquement (+ supervisor : gunicorn + celery dans 1 conteneur)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libjpeg62-turbo \
    zlib1g \
    libfreetype6 \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Copier les packages installes depuis le builder
COPY --from=builder /install /usr/local

# Copier le code source
COPY . .

# Creer les dossiers necessaires
RUN mkdir -p /app/media /app/staticfiles /app/logs

# Utilisateur non-root pour la securite
RUN addgroup --system django \
    && adduser --system --ingroup django django \
    && chown -R django:django /app

USER django

# Variables d'environnement par defaut
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=backend.settings \
    GUNICORN_WORKERS=3 \
    RUN_CELERY=true

EXPOSE 8000

COPY --chown=django:django docker/entrypoint.sh /entrypoint.sh
COPY docker/supervisord.conf /etc/supervisor/supervisord.conf
RUN chmod +x /entrypoint.sh

# L'entrypoint prepare la base (migrate, super admin, collectstatic) puis lance supervisord,
# qui fait tourner gunicorn + celery worker + celery beat. Pour un service dedie (web seul,
# ou celery seul), surcharger la commande dans Dokploy (ex. "gunicorn ..." ou "celery ...").
ENTRYPOINT ["/entrypoint.sh"]
CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf", "-n"]