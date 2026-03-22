# Démarrer tout l'environnement dev (db + redis + backend + celery)
docker compose up --build

# En arrière-plan
docker compose up -d --build

# Voir les logs
docker compose logs -f backend
docker compose logs -f celery

# Lancer une commande Django dans le container
docker compose exec backend python manage.py createsuperuser
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate

# Arrêter et supprimer les containers
docker compose down

# Tout supprimer y compris les volumes (reset BDD)
docker compose down -v