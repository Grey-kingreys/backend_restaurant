#!/bin/sh
# docker/entrypoint.sh
# Script execute au demarrage du container backend

set -e

echo "Attente de PostgreSQL..."
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
    print('PostgreSQL pret')
except Exception as e:
    print(f'Pas encore pret : {e}')
    sys.exit(1)
"; do
  sleep 2
done

echo "Application des migrations..."
python manage.py migrate --no-input

echo "Collecte des fichiers statiques..."
python manage.py collectstatic --no-input --clear

echo "Demarrage du serveur..."
exec "$@"