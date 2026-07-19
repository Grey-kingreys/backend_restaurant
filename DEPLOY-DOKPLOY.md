# Déploiement Dokploy — resfly

Topologie cible : **6 services** dans un même projet Dokploy, sur le **réseau interne** du projet.
`postgres` et `redis` sont des services dédiés Dokploy ; `backend`, `celery`, `celery-beat`
partagent **la même image** (`backend/Dockerfile`) avec des commandes différentes ; `frontend`
est une app Next.js autonome (`frontend/Dockerfile`).

```
                        Internet (HTTPS via Traefik/Dokploy)
                           │                         │
                  frontend (:3000)            backend web (:8000)
                           │                    │        │
                           └── appels API ──────┘        │  (mêmes réseau interne)
                                                  ┌───────┴────────┐
                                              postgres:5432    redis:6379
                                                  ▲   ▲            ▲   ▲
                                          celery ─┘   └─ celery-beat ─┘
```

Point clé de câblage : **les services se joignent par leur nom interne Dokploy**, pas par
`localhost`. Seuls `frontend` et `backend` ont un domaine public.

---

## 1. Services d'infrastructure (dédiés Dokploy)

### PostgreSQL
- Créer un service **Database → PostgreSQL** (v16).
- Noter : nom interne du service (ex. `resfly-db`), base, user, password.
- Pas de port public nécessaire (accès interne uniquement).

### Redis
- Créer un service **Database → Redis** (v7).
- Noter le nom interne (ex. `resfly-redis`). Pas de port public.

---

## 2. backend — service web (Application, `backend/Dockerfile`)

- **Build** : Dockerfile, contexte = `backend/`.
- **Port exposé** : `8000`. Domaine public : `https://api.mondomaine.com`.
- **Volume persistant** : monter sur `/app/media` (photos des plats). Sans S3, c'est ici
  que vivent les uploads — un volume est **obligatoire** sinon les images disparaissent à
  chaque redéploiement.

Variables d'environnement :

```env
SECRET_KEY=<clé secrète forte, 50+ caractères aléatoires>
DEBUG=False
ALLOWED_HOSTS=api.mondomaine.com
CSRF_TRUSTED_ORIGINS=https://api.mondomaine.com,https://mondomaine.com

# Base — DB_HOST = nom interne du service Postgres Dokploy
DB_NAME=resfly
DB_USER=resfly
DB_PASSWORD=<mot de passe postgres>
DB_HOST=resfly-db
DB_PORT=5432
DB_SSLMODE=disable        # 'disable' pour un Postgres interne Dokploy ; 'require' si managé/externe (Neon)

# Redis — REDIS_URL = nom interne du service Redis Dokploy
REDIS_URL=redis://resfly-redis:6379/0

# CORS — origine publique du frontend
CORS_ALLOWED_ORIGINS=https://mondomaine.com

# Emails (Resend)
RESEND_KEY=<clé API resend>
RESEND_FROM_EMAIL=noreply@mondomaine.com
FRONTEND_URL=https://mondomaine.com

# Démarrage prod : migrations committées, pas de seed de démo
RUN_MAKEMIGRATIONS=false
RUN_SEED=false
# (RUN_MIGRATIONS et RUN_COLLECTSTATIC restent true → migrate + collectstatic au boot)

# Super admin plateforme — OBLIGATOIRE en prod (le seed de démo est désactivé, donc
# aucun compte n'existe sans ça → site inaccessible). Créé/réactivé à chaque boot du web.
SUPERADMIN_PASSWORD=<mot de passe fort du super admin>
SUPERADMIN_EMAIL=admin@mondomaine.com     # sert à se connecter (login staff = email + mdp)
SUPERADMIN_LOGIN=superadmin                # optionnel (défaut: superadmin)
# SUPERADMIN_RESET_PASSWORD=true           # optionnel : force la réinit. du mdp au prochain boot
```

> L'entrypoint attend Postgres, applique `migrate`, **crée/réactive le super admin** si
> `SUPERADMIN_PASSWORD` est défini (idempotent), lance `collectstatic`, puis démarre gunicorn
> (`--workers 4`). WhiteNoise sert les fichiers statiques (admin, Swagger, DRF).
>
> Connexion : le super admin est un compte **staff** → on se connecte avec **l'email**
> (`SUPERADMIN_EMAIL`) + le mot de passe, pas avec le login.

---

## 3. celery — worker (même image, commande surchargée)

- **Même image** que le backend. **Pas de domaine, pas de port.**
- **Commande** : `celery -A backend worker --loglevel=info`
- Monter le **même volume** `/app/media` si des tâches génèrent/lisent des fichiers.

Variables : **identiques au backend** pour `DB_*` et `REDIS_URL`, plus (tout désactivé) :

```env
RUN_MAKEMIGRATIONS=false
RUN_MIGRATIONS=false
RUN_COLLECTSTATIC=false
RUN_SEED=false
# NE PAS définir SUPERADMIN_PASSWORD ici (géré par le web ; ignoré si RUN_MIGRATIONS=false)
```

> Ces flags évitent que le worker relance makemigrations/migrate/collectstatic/seed en
> parallèle du web : **un seul service** (le web) doit toucher la base au démarrage.

---

## 4. celery-beat — planificateur (même image, commande surchargée)

- **Même image**. Pas de domaine, pas de port, pas de volume media nécessaire.
- **Commande** :
  `celery -A backend beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler`

Variables : mêmes `DB_*` / `REDIS_URL` que le backend, plus (tout désactivé) :

```env
RUN_MAKEMIGRATIONS=false
RUN_MIGRATIONS=false
RUN_COLLECTSTATIC=false
RUN_SEED=false
```

> Beat déclenche notamment l'ouverture quotidienne de la Caisse Globale à 05:00
> (timezone `Africa/Conakry`). Ne lancer **qu'une seule** instance de beat, et seulement
> après que le web ait migré (beat lit la table `django_celery_beat`).

---

## 5. frontend — app Next.js (`frontend/Dockerfile`)

- **Build** : Dockerfile, contexte = `frontend/`.
- **Port exposé** : `3000`. Domaine public : `https://mondomaine.com`.

Il y a **deux façons** de dire au frontend où est le backend. Choisir l'une :

### Option A (recommandée) — `NEXT_PUBLIC_API_URL` en Build Arg

Le navigateur appelle directement `https://api.mondomaine.com`. La valeur est **inlinée au
build** (les `NEXT_PUBLIC_*` de Next sont figées à la compilation, PAS au runtime — c'est le
piège classique). Dans Dokploy, la renseigner en **Build Arg**, surtout pas en variable
runtime, sinon l'appli retombe sur le défaut relatif `/api` (jamais localhost) et n'atteint
pas le backend.

```
NEXT_PUBLIC_API_URL=https://api.mondomaine.com/api    # Build Arg (⚠️ pas runtime)
NEXT_PUBLIC_MAPBOX_TOKEN=pk.<token public mapbox>     # Build Arg
```

Nécessite : le domaine public `api.` sur le backend + `CORS_ALLOWED_ORIGINS` côté backend.

> `NEXT_PUBLIC_*` figées dans le bundle → **une image = un environnement** (2 builds pour
> staging + prod).

### Option B (runtime, sans rebuild) — routage de chemin au niveau du proxy

Une seule origine publique `mondomaine.com`. Dans Dokploy/Traefik, router
`mondomaine.com/api/*` **et** `mondomaine.com/media/*` vers le service **backend** (le reste
vers le frontend). On **ne définit pas** `NEXT_PUBLIC_API_URL` → l'appli utilise le défaut
relatif `/api` (same-origin). Aucun localhost, **CORS inutile** (même origine), et tout est
configurable au runtime.

```
# (aucune var d'URL API côté frontend)
NEXT_PUBLIC_MAPBOX_TOKEN=pk.<token public mapbox>     # Build Arg
```

Nécessite côté backend : ajouter `mondomaine.com` à `ALLOWED_HOSTS` (les requêtes /api et
/media y arrivent avec ce Host via le proxy).

> Le code frontend ne contient plus aucun `localhost:8000` : sans configuration, la base API
> est le chemin relatif `/api`.

---

## Récapitulatif des connexions

| De → Vers | Mécanisme | Valeur |
| --- | --- | --- |
| navigateur → frontend | domaine public | `https://mondomaine.com` |
| navigateur → backend (**Option A**) | Build Arg | `NEXT_PUBLIC_API_URL=https://api.mondomaine.com/api` |
| navigateur → backend (**Option B**) | routage proxy | `mondomaine.com/api` + `/media` → service backend |
| backend → postgres | réseau interne | `DB_HOST=resfly-db:5432` |
| backend/celery/beat → redis | réseau interne | `REDIS_URL=redis://resfly-redis:6379/0` |
| backend → frontend (CORS/CSRF) | env (Option A) | `CORS_ALLOWED_ORIGINS` + `CSRF_TRUSTED_ORIGINS` |
| accès initial au site | env backend | `SUPERADMIN_PASSWORD` + `SUPERADMIN_EMAIL` |

## Ordre de premier déploiement

1. `postgres` puis `redis` (services d'infra).
2. `backend` web → applique migrations + collectstatic (attend automatiquement Postgres).
3. `celery` et `celery-beat`.
4. `frontend`.

## Notes / dette à surveiller

- **Médias** : servis par Django (`django.views.static.serve`) depuis le volume `/app/media`.
  Correct pour l'échelle actuelle ; pour un fort trafic, migrer vers S3
  (`USE_S3=True` — nécessite d'ajouter `django-storages` + `boto3` à `requirements.txt`, non
  installés aujourd'hui) ou faire servir `/media/` par le reverse-proxy.
- **`--legacy-peer-deps`** au build frontend : dû à `@testing-library/react@14` (peer React 18)
  face à React 19. À retirer une fois testing-library passé en v16+.
- **Seed de démo** : `RUN_SEED=false` en prod pour ne pas injecter les restaurants de démo.
