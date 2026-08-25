# Backend - RestoPro

API Django REST Framework multi-tenant SaaS pour la gestion de restaurants.

## Commandes essentielles

**Toujours passer par Docker. Ne jamais créer de venv local.**

```bash
# Depuis /backend/
docker compose up -d                  # démarre db + redis + backend (seed auto au démarrage)
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo   # idempotent (no-op si déjà fait)
docker compose exec backend python manage.py shell
docker compose logs -f backend
```

## Seed de démo

**Fichier** : `apps/company/management/commands/seed_demo.py`

Le seed s'exécute **automatiquement** à chaque démarrage du conteneur via `docker/entrypoint.sh` (étape 4/5). Il est **idempotent** : si `Restaurant(nom="Le Baobab")` existe déjà, il se termine sans erreur ni modification.

Ce qu'il crée (dates relatives à `today`) :

- 2 restaurants (Le Baobab, Chez Mariama)
- 13 utilisateurs - tous les rôles pour Le Baobab + admin/comptable pour Chez Mariama + 1 superadmin global
- 12 plats (10 pour Le Baobab, 2 pour Chez Mariama)
- 4 tables pour Le Baobab
- Caisses générales, 6 caisses globales fermées (J-6 → J-1) + 1 ouverte aujourd'hui, 1 caisse comptable
- 27 commandes sur 7 jours (payées en J-6..J-1, actives aujourd'hui), avec items, paiements, remises
- Dépenses sur J-2, J-1 et aujourd'hui

**Mot de passe de tous les utilisateurs** : `Soul2001`

| Login | Rôle | Restaurant |
| --- | --- | --- |
| `superadmin` | Rsuper_admin | - |
| `lebaobab_admin` | Radmin | Le Baobab |
| `lebaobab_manager` | Rmanager | Le Baobab |
| `lebaobab_serveur` | Rserveur | Le Baobab |
| `lebaobab_chef` | Rchef_cuisinier | Le Baobab |
| `lebaobab_cuisinier` | Rcuisinier | Le Baobab |
| `lebaobab_comptable` | Rcomptable | Le Baobab |
| `lebaobab_table_01..04` | Rtable | Le Baobab |
| `chezmariama_admin` | Radmin | Chez Mariama |
| `chezmariama_comptable` | Rcomptable | Chez Mariama |

> **Important** : `Commande.date_commande` est `auto_now_add=True`. Le seed utilise
> `Commande.objects.filter(pk=...).update(date_commande=...)` pour injecter des dates
> historiques après création - c'est la seule façon de contourner `auto_now_add`.

## Architecture

### Stack

- Django 4.x + Django REST Framework
- PostgreSQL (SQLite fallback si `DB_NAME` absent du `.env`)
- Redis + Celery + Celery Beat
- SimpleJWT avec rotation et blacklist
- drf-spectacular (Swagger à `/api/docs/`)
- django-prometheus (métriques à `/metrics`)
- Resend API pour les emails transactionnels (pas SMTP)
- Stockage local en dev, S3 en prod (`USE_S3=True`)
- OpenTelemetry vers Tempo (stack obs commentée, voir ci-dessous)

### Apps

| App | Rôle |
| --- | --- |
| `apps.company` | `Restaurant` (tenant SaaS) + `OnboardingToken` + commande `seed_demo` |
| `apps.accounts` | `User`, auth JWT, CRUD utilisateurs, impersonation |
| `apps.restaurant` | `TableRestaurant`, `TableToken` (QR), `TableSession` |
| `apps.menu` | `Plat` avec catégories et flag validation cuisine |
| `apps.commandes` | `PanierItem`, `Commande` (workflow), `CommandeItem` |
| `apps.paiements` | Flux de caisse complet (5 modèles) |
| `apps.dashboard` | Agrégats pour le tableau de bord - endpoint unique `/api/dashboard/stats/` |

### Isolation SaaS

Chaque queryset filtre sur `restaurant=request.user.restaurant`. La permission `IsRestaurantActive` bloque toute action si `restaurant.is_active=False`. Le `restaurant_id` est dupliqué en FK directe sur `Commande` pour des requêtes performantes sans JOIN sur `User`.

## Modèles

### `company.Restaurant`

- `is_active` : suspension du tenant
- `get_slug()` : préfixe pour les logins (`lebaobab_`)
- `OnboardingToken` : UUID 48h pour le premier login admin

### `accounts.User`

- `USERNAME_FIELD = 'login'` - champ d'identification par défaut
- `login` généré automatiquement : `{slug}_{role}_{n}`
- `email` unique et nullable (null pour `Rtable`)
- `must_change_password` : force le changement au premier login
- `restaurant` nullable uniquement pour `Rsuper_admin`
- 8 rôles : `Rsuper_admin`, `Radmin`, `Rmanager`, `Rserveur`, `Rchef_cuisinier`, `Rcuisinier`, `Rcomptable`, `Rtable`

### `restaurant.TableRestaurant`

- `OneToOne` avec un `User` de rôle `Rtable`
- `get_statut_actuel()` : dérive le statut de la table depuis les commandes actives
- `TableToken` : token URL-safe 64 chars encodé dans le QR Code - invalide si le mdp change
- `TableSession` : créée à chaque scan QR, expire 1 min après le paiement

### `menu.Plat`

- `necessite_validation_cuisine` : si True, la commande passe par `EN_ATTENTE → PRETE` avant `SERVIE`
- `disponible` : soft-delete (masque le plat sans le supprimer)
- Custom manager `PlatDisponibleManager` : filtre `disponible=True` par défaut

### `commandes.Commande`

Workflow d'état : `EN_ATTENTE → PRETE → SERVIE → PAYEE`

- `date_commande` : `auto_now_add=True` - contourner avec `.update()` pour les seeds/tests
- `PanierItem` : panier DB, unique par `(table, plat)`
- `CommandeItem` : snapshot du prix au moment de la commande
- FK directe `restaurant` pour filtrage sans JOIN

### `paiements` - Flux de caisse

| Modèle | Rôle |
| --- | --- |
| `CaisseGenerale` | 1:1 Restaurant, permanente, jamais clôturée |
| `CaisseGlobale` | Journalière, ouvre à 5h via Celery Beat, `fermer()` irréversible → transfère vers CaisseGenerale |
| `CaisseComptable` | Session par comptable (`opened_at` : auto_now_add) |
| `RemiseServeur` | Remise physique du serveur au comptable - lié via `paiement__commande__restaurant` |
| `Paiement` | 1:1 avec Commande (`date_paiement` : auto_now_add) |
| `Depense` | Dépenses saisies par le comptable (`date_depense` : DateField settable) |

## Dashboard API

**Endpoint** : `GET /api/dashboard/stats/`

**Vue** : `apps/dashboard/views.py` - `DashboardView`

Retourne des données différentes selon `request.user.role` :

| type retourné | Rôles concernés | Données clés |
| --- | --- | --- |
| `admin` | Radmin, Rmanager | kpis, revenus_7j, statuts_live, par_categorie, par_heure, top_plats, dernieres_commandes |
| `serveur` | Rserveur | tables_statuts, commandes_pretes, par_heure, commandes_traitees_7j |
| `cuisine` | Rchef_cuisinier, Rcuisinier | file_commandes, par_categorie, par_heure, oldest_wait_mins |
| `comptable` | Rcomptable | caisse, balance_7j, dernieres_remises, solde_generale |
| `table` | Rtable | commande_active, suggestions, nb_plats_disponibles |
| `superadmin` | Rsuper_admin | stats_restaurants, revenus_7j global |

## Auth & Sécurité

### Endpoints auth (`/api/accounts/auth/`)

| Route | Vue | Accès |
| --- | --- | --- |
| `POST /login/` | `LoginView` | Public - email+mdp (staff) ou login+mdp (table) |
| `POST /logout/` | `LogoutView` | Authentifié - blackliste le refresh token |
| `GET /me/` | `MeView` | Authentifié - profil complet |
| `POST /change-password/` | `ChangePasswordView` | Authentifié - aussi utilisé au first-login |
| `POST /password-reset/` | `PasswordResetRequestView` | Public - envoie email via Resend |
| `POST /password-reset/confirm/` | `PasswordResetConfirmView` | Public - UUID token 1h |
| `POST /token/refresh/` | SimpleJWT | Public - rotation avec blacklist |

### Impersonation

**Fichier** : `apps/accounts/api_views.py` - `ImpersonateView`

**Route** : `POST /api/accounts/auth/users/<pk>/impersonate/`

**Permission** : `IsAuthenticated + IsAdmin + IsRestaurantActive`

**Réponse** : `{ success: true, data: { access, refresh, user } }` - vrais tokens JWT pour la cible.

Règles de sécurité :

- Même restaurant obligatoire
- Ne peut pas se simuler soi-même
- Impossible de simuler un `Rsuper_admin` ou `Radmin`
- Impossible de simuler un utilisateur inactif (`actif=False`)

Rôles simulables : `Rmanager`, `Rserveur`, `Rchef_cuisinier`, `Rcuisinier`, `Rcomptable`, `Rtable`

### Permissions personnalisées (`apps/accounts/permissions.py`)

- `IsAdmin` - rôle `Radmin`
- `IsAdminOrManager` - rôle `Radmin` ou `Rmanager`
- `IsRestaurantActive` - vérifie `restaurant.is_active`
- `IsSameRestaurant` - vérifie que la ressource cible appartient au même restaurant

## Celery

**Configuration** : `backend/celery.py`

- Timezone : `Africa/Conakry`
- Task time limit : 5 min (soft 4 min)
- Beat scheduler : `DatabaseScheduler` (table en BDD)

**Tâche active** : `ouvrir_caisse_globale_quotidienne` - tous les jours à 05:00

**Tâche paiement** : `creer_remise_pour_paiement` - se déclenche quand une commande passe en statut `PAYÉE`. Si aucune `CaisseGlobale` n'est ouverte à ce moment, la remise **n'est pas créée** (warning log silencieux).

> En développement sans Celery actif, la CaisseGlobale doit être ouverte manuellement :
> `POST /api/paiements/caisse-globale/ouvrir/` (Admin uniquement)

## Emails

**Ne pas utiliser Django EMAIL_BACKEND SMTP.** L'app utilise le SDK Resend directement.

- `RESEND_KEY` : clé API Resend
- `RESEND_FROM_EMAIL` : expéditeur (ex. `noreply@kingreys.fr`)
- `FRONTEND_URL` : utilisé dans les liens des emails (`http://localhost:3000` en dev)

## Docker Compose

Le fichier `docker-compose.yml` fait tourner **3 services** : `db`, `redis`, `backend`.

`docker/entrypoint.sh` exécute dans l'ordre :

1. Attente PostgreSQL
2. `makemigrations` (toutes les apps)
3. `migrate`
4. `seed_demo` (idempotent)
5. `collectstatic`

La stack d'observabilité (loki, mimir, cadvisor, prometheus, tempo, grafana) est **commentée** avec le marqueur `# [OBS]`. Pour la réactiver : décommenter tous les blocs `# [OBS]` et décommenter les variables `OTEL_*` sur le service `backend`.

## Variables d'environnement (`.env`)

```text
SECRET_KEY
DEBUG
ALLOWED_HOSTS
DB_NAME / DB_USER / DB_PASSWORD / DB_HOST / DB_PORT / DB_SSLMODE
REDIS_URL
JWT_ACCESS_TOKEN_LIFETIME_MINUTES   (défaut: 60)
JWT_REFRESH_TOKEN_LIFETIME_DAYS     (défaut: 7)
CORS_ALLOWED_ORIGINS                (ex. http://localhost:3000)
RESEND_KEY
RESEND_FROM_EMAIL
FRONTEND_URL
USE_S3                              (False en dev)
AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_STORAGE_BUCKET_NAME
AWS_S3_REGION_NAME / AWS_S3_LOCATION / AWS_S3_CUSTOM_DOMAIN
OTEL_EXPORTER_OTLP_ENDPOINT        (stack obs seulement)
OTEL_SERVICE_NAME                  (stack obs seulement)
GRAFANA_USER / GRAFANA_PASSWORD    (stack obs seulement)
```

## API - structure des réponses

Toutes les réponses suivent la même enveloppe :

```json
{ "success": true, "data": {}, "message": "..." }
{ "success": false, "errors": {}, "message": "..." }
```

Fonctions helper dans `api_views.py` : `success_response()` et `error_response()`.

## Swagger

Accessible à `/api/docs/` (ReDoc et Swagger UI). Schéma OpenAPI généré par drf-spectacular. Chaque vue est annotée avec `@extend_schema`.
