#!/bin/sh

set -e

echo "========================================"
echo " Restaurant Manager Pro — Demarrage"
echo "========================================"

# Chaque etape est pilotable par variable d'env (defaut : activee = comportement dev).
# En prod Dokploy :
#   - service web        : RUN_MAKEMIGRATIONS=false RUN_SEED=false (migrate + collectstatic restent true)
#   - worker / beat celery : RUN_MIGRATIONS=false RUN_COLLECTSTATIC=false RUN_SEED=false
#     (un seul service doit toucher la base au demarrage)
RUN_MIGRATIONS="${RUN_MIGRATIONS:-true}"
RUN_MAKEMIGRATIONS="${RUN_MAKEMIGRATIONS:-true}"
RUN_SEED="${RUN_SEED:-true}"
RUN_COLLECTSTATIC="${RUN_COLLECTSTATIC:-true}"

# ── 1. Attente PostgreSQL ─────────────────────────────────────────────────
echo "[1/5] Attente de PostgreSQL..."
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
  echo "[2/5] Generation des migrations..."
  for app in company accounts menu restaurant commandes paiements dashboard; do
    python manage.py makemigrations "$app" --no-input || echo "  [WARN] $app : pas de changement"
  done
else
  echo "[2/5] Makemigrations ignore (RUN_MAKEMIGRATIONS=false)"
fi

# ── 3. Migrate ────────────────────────────────────────────────────────────
if [ "$RUN_MIGRATIONS" = "true" ]; then
  echo "[3/5] Application des migrations..."
  python manage.py migrate --no-input
else
  echo "[3/5] Migrate ignore (RUN_MIGRATIONS=false)"
fi

# ── 3bis. Super admin plateforme (prod) ───────────────────────────────────
# S'exécute là où les migrations tournent (service web) si SUPERADMIN_PASSWORD est
# défini. Idempotent. Débloque l'accès quand le seed de démo est désactivé.
if [ "$RUN_MIGRATIONS" = "true" ] && [ -n "$SUPERADMIN_PASSWORD" ]; then
  echo "[*] Création/réactivation du super admin..."
  python manage.py create_superadmin
fi

# ── 4. Seed de demo (idempotent) ──────────────────────────────────────────
if [ "$RUN_SEED" = "true" ]; then
  echo "[4/5] Seed des donnees de demo..."
  python manage.py seed_demo
else
  echo "[4/5] Seed ignore (RUN_SEED=false)"
fi

# ── 5. Collectstatic ─────────────────────────────────────────────────────
if [ "$RUN_COLLECTSTATIC" = "true" ]; then
  echo "[5/5] Collectstatic..."
  python manage.py collectstatic --no-input --clear
else
  echo "[5/5] Collectstatic ignore (RUN_COLLECTSTATIC=false)"
fi

echo "========================================"
echo " Demarrage du serveur..."
echo "========================================"

exec "$@"
