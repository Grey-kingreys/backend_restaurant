#!/bin/sh

set -e

echo "========================================"
echo " Restaurant Manager Pro — Demarrage"
echo "========================================"

# Chaque etape est pilotable par variable d'env (defaut : activee = comportement dev).
#
# Deux « seeds » INDEPENDANTS, avec des regles differentes :
#   - Super admin (create_superadmin) : bootstrap ESSENTIEL, s'execute en PROD *et* en dev.
#     Piloté par SUPERADMIN_PASSWORD (rien a voir avec RUN_SEED). Sans lui, pas d'acces au site.
#   - Seed de demo (seed_demo)        : donnees de demonstration, DEV UNIQUEMENT.
#     Piloté par RUN_SEED — a mettre a false en prod pour ne pas injecter les restos de demo.
#
# En prod Dokploy :
#   - service web          : RUN_MAKEMIGRATIONS=false RUN_SEED=false + SUPERADMIN_PASSWORD=...
#                            (migrate + collectstatic + create_superadmin restent actifs)
#   - worker / beat celery : RUN_MIGRATIONS=false RUN_COLLECTSTATIC=false RUN_SEED=false
#                            (un seul service — le web — doit toucher la base au demarrage)
RUN_MIGRATIONS="${RUN_MIGRATIONS:-true}"
RUN_MAKEMIGRATIONS="${RUN_MAKEMIGRATIONS:-true}"
RUN_SEED="${RUN_SEED:-true}"
RUN_COLLECTSTATIC="${RUN_COLLECTSTATIC:-true}"

# ── 1. Attente PostgreSQL ─────────────────────────────────────────────────
echo "[1/6] Attente de PostgreSQL..."
until python -c "
import psycopg, os, sys
try:
    conn = psycopg.connect(
        dbname=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT', '5432'),
    )
    conn.close()
    print('  PostgreSQL pret')
except Exception as e:
    print(f'  Pas encore pret : {e}')
    sys.exit(1)
"; do
  sleep 2
done

# ── 2. Makemigrations (dev uniquement — en prod les migrations sont committees) ──
if [ "$RUN_MAKEMIGRATIONS" = "true" ]; then
  echo "[2/6] Generation des migrations..."
  for app in company accounts menu restaurant commandes paiements dashboard; do
    python manage.py makemigrations "$app" --no-input || echo "  [WARN] $app : pas de changement"
  done
else
  echo "[2/6] Makemigrations ignore (RUN_MAKEMIGRATIONS=false)"
fi

# ── 3. Migrate ────────────────────────────────────────────────────────────
if [ "$RUN_MIGRATIONS" = "true" ]; then
  echo "[3/6] Application des migrations..."
  python manage.py migrate --no-input
else
  echo "[3/6] Migrate ignore (RUN_MIGRATIONS=false)"
fi

# ── 4. Super admin plateforme (PROD + DEV) ────────────────────────────────
# Seed ESSENTIEL, indépendant de RUN_SEED : s'exécute dès que SUPERADMIN_PASSWORD est
# défini, sur le service qui applique les migrations (le web). Idempotent.
if [ -n "$SUPERADMIN_PASSWORD" ]; then
  if [ "$RUN_MIGRATIONS" = "true" ]; then
    echo "[4/6] Création/réactivation du super admin..."
    python manage.py create_superadmin
  else
    echo "[4/6] Super admin ignore ici (RUN_MIGRATIONS=false — géré par le service web)"
  fi
else
  echo "[4/6] Super admin ignore (SUPERADMIN_PASSWORD non défini)"
fi

# ── 5. Seed de demo (DEV UNIQUEMENT, idempotent) ──────────────────────────
# Données de démonstration. RUN_SEED=false en prod → ne s'exécute PAS.
if [ "$RUN_SEED" = "true" ]; then
  echo "[5/6] Seed des donnees de demo..."
  python manage.py seed_demo
else
  echo "[5/6] Seed de démo ignore (RUN_SEED=false)"
fi

# ── 6. Collectstatic ─────────────────────────────────────────────────────
if [ "$RUN_COLLECTSTATIC" = "true" ]; then
  echo "[6/6] Collectstatic..."
  python manage.py collectstatic --no-input --clear
else
  echo "[6/6] Collectstatic ignore (RUN_COLLECTSTATIC=false)"
fi

echo "========================================"
echo " Demarrage du serveur..."
echo "========================================"

exec "$@"
