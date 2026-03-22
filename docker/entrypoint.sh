#!/bin/sh
# docker/entrypoint.sh
# Script execute au demarrage du container backend
# Note : migrate et collectstatic sont geres dans docker-compose.yml
# via la commande de chaque service - pas ici

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

echo "Demarrage..."
exec "$@"