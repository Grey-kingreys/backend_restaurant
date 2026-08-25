# Déploiement Dokploy - resfly

Topologie cible : **4 services** dans un même projet Dokploy, sur le **réseau interne** du projet.
`postgres` et `redis` sont des services dédiés Dokploy ; le `backend` est **un seul conteneur
tout-en-un** (`backend/Dockerfile`) qui fait tourner gunicorn + Celery worker + Celery beat via
`supervisord` (pas besoin de compose ni de services Celery séparés) ; `frontend` est une app
Next.js autonome (`frontend/Dockerfile`).

```
                        Internet (HTTPS via Traefik/Dokploy)
                           │                         │
                  frontend (:3000)            backend (:8000)  ── conteneur unique ──┐
                           │                    │     supervisord ┬ gunicorn (web)    │
                           └── appels API ──────┘                 ├ celery worker     │
                                                  ┌───────────────┤ celery beat       │
                                              postgres:5432   redis:6379 ◄────────────┘
```

Point clé de câblage : **les services se joignent par leur nom interne Dokploy**, pas par
`localhost`. Seuls `frontend` et `backend` ont un domaine public.

> Celery tourne **dans le conteneur backend** (démarré automatiquement par supervisord,
> `RUN_CELERY=true` par défaut). Voir §3. Rien à lancer manuellement.

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

## 2. backend - service web (Application, `backend/Dockerfile`)

- **Build** : Dockerfile, contexte = `backend/`.
- **Port exposé** : `8000`. Domaine public : `https://api.mondomaine.com`.
- **Volume persistant** : monter sur `/app/media` (photos des plats). Sans S3, c'est ici
  que vivent les uploads - un volume est **obligatoire** sinon les images disparaissent à
  chaque redéploiement.

Variables d'environnement :

```env
SECRET_KEY=<clé secrète forte, 50+ caractères aléatoires>
DEBUG=False
ALLOWED_HOSTS=api.mondomaine.com
CSRF_TRUSTED_ORIGINS=https://api.mondomaine.com,https://mondomaine.com

# Base - DB_HOST = nom interne du service Postgres Dokploy
DB_NAME=resfly
DB_USER=resfly
DB_PASSWORD=<mot de passe postgres>
DB_HOST=resfly-db
DB_PORT=5432
DB_SSLMODE=disable        # 'disable' pour un Postgres interne Dokploy ; 'require' si managé/externe (Neon)

# Redis - REDIS_URL = nom interne du service Redis Dokploy
REDIS_URL=redis://resfly-redis:6379/0

# CORS - origine publique du frontend
CORS_ALLOWED_ORIGINS=https://mondomaine.com

# Emails (Resend)
RESEND_KEY=<clé API resend>
RESEND_FROM_EMAIL=noreply@mondomaine.com
FRONTEND_URL=https://mondomaine.com

# Démarrage prod : migrations committées, pas de seed de démo
RUN_MAKEMIGRATIONS=false
RUN_SEED=false
# (RUN_MIGRATIONS et RUN_COLLECTSTATIC restent true → migrate + collectstatic au boot)

# Super admin plateforme - OBLIGATOIRE en prod (le seed de démo est désactivé, donc
# aucun compte n'existe sans ça → site inaccessible). Créé/réactivé à chaque boot du web.
# ⚠️ PASSWORD *et* EMAIL sont requis : la connexion staff se fait par EMAIL (pas le login),
# donc sans SUPERADMIN_EMAIL le compte n'est pas créé (il serait inutilisable).
SUPERADMIN_PASSWORD=<mot de passe fort du super admin>   # requis
SUPERADMIN_EMAIL=admin@mondomaine.com                    # requis - identifiant de connexion
SUPERADMIN_LOGIN=superadmin                              # optionnel (défaut: superadmin)
# SUPERADMIN_RESET_PASSWORD=true                         # optionnel : force la réinit. du mdp au boot
```

Options facultatives (déjà des valeurs par défaut dans l'image) :

```env
GUNICORN_WORKERS=3        # nb de workers gunicorn (défaut 3)
RUN_CELERY=true           # démarre celery worker + beat dans ce conteneur (défaut true)
```

> L'entrypoint attend Postgres, applique `migrate`, **crée/réactive le super admin** si
> `SUPERADMIN_PASSWORD` est défini (idempotent), lance `collectstatic`, puis démarre
> **supervisord** qui fait tourner gunicorn + Celery worker + Celery beat. WhiteNoise sert
> les fichiers statiques (admin, Swagger, DRF).
>
> Connexion : le super admin est un compte **staff** → on se connecte avec **l'email**
> (`SUPERADMIN_EMAIL`) + le mot de passe, pas avec le login.

---

## 3. Celery - intégré au conteneur backend (aucun service à créer)

**Rien à faire de plus** : le worker et le beat démarrent **automatiquement** dans le conteneur
backend, gérés par `supervisord` (`docker/supervisord.conf`). Démarrage auto + **redémarrage
auto** si un process crashe, logs redirigés vers la sortie du conteneur (visibles dans Dokploy).

- **celery worker** : `celery -A backend worker` - exécute les tâches (ex. `creer_remise_pour_paiement`).
- **celery beat** : `celery -A backend beat` (DatabaseScheduler) - déclenche les tâches
  périodiques (ex. ouverture de la Caisse Globale à 05:00, timezone `Africa/Conakry`).

Ils utilisent le même `REDIS_URL` / `DB_*` que gunicorn (même conteneur). Monter le volume
`/app/media` sur le backend suffit (partagé par tout le conteneur).

> ⚠️ **beat = une seule horloge** : ne **pas** scaler ce conteneur au-delà de **1 réplique**,
> sinon plusieurs beat → tâches périodiques dupliquées. Pour scaler l'app, il faut sortir
> Celery (voir ci-dessous).

**Pour désactiver Celery ici** (ex. si tu veux le faire tourner ailleurs) : `RUN_CELERY=false`.

**Option avancée - sortir Celery dans des services dédiés** (pour scaler le web à plusieurs
répliques) : créer 1 ou 2 apps Dokploy supplémentaires sur la **même image**, en surchargeant
la commande (`celery -A backend worker -l info` / `celery -A backend beat -l info`) et avec
`RUN_MAKEMIGRATIONS=false RUN_MIGRATIONS=false RUN_COLLECTSTATIC=false RUN_SEED=false`
(pour qu'un seul service touche la base). Mettre alors `RUN_CELERY=false` sur le web.

---

## 4. frontend - app Next.js (`frontend/Dockerfile`)

- **Build** : Dockerfile, contexte = `frontend/`.
- **Port exposé** : `3000`. Domaine public : `https://mondomaine.com`.

### `NEXT_PUBLIC_API_URL` est configurable au RUNTIME (recommandé)

Les `NEXT_PUBLIC_*` de Next sont normalement figées au build. L'image frontend contourne ça :
elle compile avec des **sentinelles** qu'un entrypoint remplace au démarrage par les valeurs
de l'environnement du conteneur. Résultat : tu poses simplement une **variable d'env Dokploy**
(pas un Build Arg), et un **redémarrage** suffit - pas besoin de rebuild par environnement.

```env
NEXT_PUBLIC_API_URL=https://api.mondomaine.com/api    # variable d'env RUNTIME (pas Build Arg)
NEXT_PUBLIC_MAPBOX_TOKEN=pk.<token public mapbox>     # runtime aussi
```

- Bien mettre **`/api` à la fin** et le **même schéma** (`https://`) que le backend.
- Nécessite : domaine public du backend + `CORS_ALLOWED_ORIGINS` = domaine frontend côté backend.
- Non défini → défaut relatif `/api` (jamais localhost) → utile si tu routes `/api` et `/media`
  vers le backend au niveau du proxy Dokploy (une seule origine, CORS inutile).

> Le Build Arg reste possible (`--build-arg NEXT_PUBLIC_API_URL=…`) : la valeur est alors
> **figée** dans l'image et l'env runtime est ignoré. Préfère l'env runtime - c'est ce qui
> évite le piège « build arg non transmis → l'app tape son propre domaine → 404 ».

---

## Récapitulatif des connexions

| De → Vers | Mécanisme | Valeur |
| --- | --- | --- |
| navigateur → frontend | domaine public | `https://mondomaine.com` |
| navigateur → backend (**Option A**) | Build Arg | `NEXT_PUBLIC_API_URL=https://api.mondomaine.com/api` |
| navigateur → backend (**Option B**) | routage proxy | `mondomaine.com/api` + `/media` → service backend |
| backend → postgres | réseau interne | `DB_HOST=resfly-db:5432` |
| backend (web+celery) → redis | réseau interne | `REDIS_URL=redis://resfly-redis:6379/0` |
| backend → frontend (CORS/CSRF) | env (Option A) | `CORS_ALLOWED_ORIGINS` + `CSRF_TRUSTED_ORIGINS` |
| accès initial au site | env backend | `SUPERADMIN_PASSWORD` + `SUPERADMIN_EMAIL` |

## Ordre de premier déploiement

1. `postgres` puis `redis` (services d'infra).
2. `backend` → migrate + collectstatic + super admin, puis supervisord lance gunicorn +
   Celery worker + beat (le tout dans ce conteneur ; attend automatiquement Postgres).
3. `frontend`.

## Notes / dette à surveiller

- **Médias** : servis par Django (`django.views.static.serve`) depuis le volume `/app/media`.
  Correct pour l'échelle actuelle ; pour un fort trafic, migrer vers S3
  (`USE_S3=True` - nécessite d'ajouter `django-storages` + `boto3` à `requirements.txt`, non
  installés aujourd'hui) ou faire servir `/media/` par le reverse-proxy.
- ~~`--legacy-peer-deps` au build frontend~~ : réglé - `@testing-library/react` est passé en
  v16 (compatible React 19), le Dockerfile utilise `npm ci` sans flag.
- **Seed de démo** : `RUN_SEED=false` en prod pour ne pas injecter les restaurants de démo.

---

## 8. Changer de nom de domaine

Le point critique : **les QR codes collés sur les tables encodent le domaine** au moment de leur
impression (`TableToken.get_qr_url()` → `FRONTEND_URL/auth/qr/<token>/`). Un QR imprimé sous
l'ancien domaine doit continuer à fonctionner, sinon il faut réimprimer tous les QR de tous les
restaurants. Idem pour les liens de livraison déjà envoyés aux livreurs et les liens de suivi
contenus dans les SMS de reçu. **L'ancien domaine ne doit donc jamais être débranché.**

### Côté frontend (déjà en place dans le code)

Deux variables d'environnement classiques sur le service frontend, **sans rebuild** :

```text
CANONICAL_HOST=resfly.org
LEGACY_HOSTS=resfly.kingreys.fr,www.resfly.kingreys.fr    # 3 anciens domaines maximum
```

La redirection est un **308** (préserve méthode, corps et query) qui conserve le chemin.

⚠️ **Pourquoi ce n'est pas une simple variable d'env** : Next fige `redirects()` au BUILD, dans
`.next/routes-manifest.json`. Une variable posée au seul démarrage du conteneur n'aurait
**aucun effet** - la redirection ne se produirait jamais, silencieusement, et tous les QR codes
déjà imprimés cesseraient de fonctionner. Le build compile donc des **sentinelles**
(`RUNTIME_LEGACY_HOST_1_PLACEHOLDER`...) que `docker/entrypoint.sh` remplace au démarrage,
exactement comme pour les `NEXT_PUBLIC_*`. Un emplacement non utilisé reste inerte : aucun
en-tête `Host` réel ne peut valoir une sentinelle.

Rien n'est substitué si `CANONICAL_HOST` est absent : sans ce garde-fou, les visiteurs de
l'ancien domaine seraient envoyés vers un hôte bidon. Le dev local n'est pas affecté.

Une URL de QR (`/auth/qr/<token>/`) passe par 2 sauts : Next normalise d'abord le slash final,
puis redirige vers le domaine canonique. C'est imperceptible.

### Côté Dokploy / DNS

1. DNS : `resfly.org` et `api.resfly.org` → même IP serveur.
2. **Garder l'ancien domaine attaché au service frontend** dans Dokploy, avec son certificat
   TLS valide. Un certificat expiré sur l'ancien domaine bloquerait le navigateur **avant**
   que la redirection ne s'applique - le QR échouerait malgré tout.
3. Ajouter le nouveau domaine au service frontend (port 3000) et `api.resfly.org` au backend
   (port **8000**, pas 3000 - cf. piège n°1 plus haut).

### Côté backend (variables d'environnement)

```text
ALLOWED_HOSTS=api.resfly.org,api.resfly.kingreys.fr    # garder les deux
CORS_ALLOWED_ORIGINS=https://resfly.org                 # le nouveau suffit
CSRF_TRUSTED_ORIGINS=https://resfly.org
FRONTEND_URL=https://resfly.org                         # nouveaux QR et liens d'emails
```

`FRONTEND_URL` ne change que les liens **générés à partir de maintenant** ; les anciens QR
restent couverts par la redirection.

### ⚠️ Ne PAS rediriger le domaine de l'API

`api.resfly.kingreys.fr` doit continuer à **servir l'API directement**, sans redirection.
Une redirection inter-origine sur un appel authentifié fait tomber l'en-tête `Authorization`
et casse le préflight CORS. Il suffit de garder l'ancien hôte dans `ALLOWED_HOSTS` : une fois
`NEXT_PUBLIC_API_URL` basculé, plus rien ne l'appellera, à part d'éventuels onglets encore
ouverts avec l'ancien bundle.

### Vérification après bascule

```bash
curl -sI https://resfly.kingreys.fr/menu | grep -i '^location'   # → https://resfly.org/menu
curl -sI https://resfly.org/menu | head -1                        # → 200, pas de redirection
```

Et surtout : **scanner un QR déjà imprimé** avec un vrai téléphone.

