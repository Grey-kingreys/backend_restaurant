#!/bin/sh

set -e

echo "========================================"
echo " Restaurant Manager Pro — Demarrage"
echo "========================================"

# ── 1. Attente PostgreSQL ─────────────────────────────────────────────────
echo "[1/4] Attente de PostgreSQL..."
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

# ── 2. Makemigrations ─────────────────────────────────────────────────────
echo "[2/4] Generation des migrations..."

python manage.py makemigrations company    --no-input || echo "  [WARN] company : pas de changement"
python manage.py makemigrations accounts  --no-input || echo "  [WARN] accounts : pas de changement"
python manage.py makemigrations menu      --no-input || echo "  [WARN] menu : pas de changement"
python manage.py makemigrations restaurant --no-input || echo "  [WARN] restaurant : pas de changement"
python manage.py makemigrations commandes --no-input || echo "  [WARN] commandes : pas de changement"
python manage.py makemigrations paiements --no-input || echo "  [WARN] paiements : pas de changement"
python manage.py makemigrations dashboard --no-input || echo "  [WARN] dashboard : pas de changement"

# ── 3. Migrate ────────────────────────────────────────────────────────────
echo "[3/4] Application des migrations..."
python manage.py migrate --no-input

# ── 4. Collectstatic ─────────────────────────────────────────────────────
echo "[4/4] Collectstatic..."
python manage.py collectstatic --no-input --clear

echo "========================================"
echo " Demarrage du serveur..."
echo "========================================"
echo " URL : http://localhost:8000"
echo "========================================"

exec "$@"