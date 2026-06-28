# apps/accounts/perm_codes.py
# Codes de permissions centralisés — source de vérité unique.
# Importez ces constantes partout où vous avez besoin de vérifier une permission.

# ── Équipe ────────────────────────────────────────────────────────────────────
PERM_MANAGE_EQUIPE   = 'manage_equipe'    # CRUD users, toggle, reset password
PERM_IMPERSONATE     = 'impersonate'      # Simuler un membre
PERM_MANAGE_ROLES    = 'manage_roles'     # Créer / modifier les rôles custom

# ── Menu ──────────────────────────────────────────────────────────────────────
PERM_MANAGE_MENU     = 'manage_menu'      # Créer / modifier / supprimer / toggle plats

# ── Commandes ─────────────────────────────────────────────────────────────────
PERM_VIEW_COMMANDES    = 'view_commandes'    # Voir toutes les commandes du resto
PERM_MANAGE_COMMANDES  = 'manage_commandes'  # Marquer servie / payée / supprimer

# ── Cuisine ───────────────────────────────────────────────────────────────────
PERM_VIEW_CUISINE    = 'view_cuisine'     # Voir la file d'attente cuisine
PERM_MANAGE_CUISINE  = 'manage_cuisine'   # Marquer une commande comme prête

# ── Tables ────────────────────────────────────────────────────────────────────
PERM_MANAGE_TABLES   = 'manage_tables'    # CRUD tables + génération QR
PERM_VIEW_TABLES     = 'view_tables'      # Voir les tables et leur statut

# ── Finance ───────────────────────────────────────────────────────────────────
PERM_MANAGE_CAISSE_COMPTABLE = 'manage_caisse_comptable'  # Caisse du jour (ouvrir/dépenses/fermer)
PERM_VIEW_CAISSE_GLOBALE     = 'view_caisse_globale'      # Voir la caisse globale journalière
PERM_MANAGE_CAISSE_GLOBALE   = 'manage_caisse_globale'    # Fermer / ouvrir manuellement
PERM_VIEW_CAISSE_GENERALE    = 'view_caisse_generale'     # Voir la caisse générale permanente
PERM_VIEW_REMISES            = 'view_remises'             # Voir ses propres remises
PERM_MANAGE_REMISES          = 'manage_remises'           # Valider les remises des serveurs

# ── Restaurant ────────────────────────────────────────────────────────────────
PERM_MANAGE_RESTAURANT = 'manage_restaurant'  # Modifier les paramètres du restaurant


# ── Catalogue complet ─────────────────────────────────────────────────────────
# (code, label, catégorie)
ALL_PERMISSIONS = [
    # Équipe
    (PERM_MANAGE_EQUIPE,            "Gérer l'équipe",                       "Équipe"),
    (PERM_IMPERSONATE,              "Simuler un membre",                    "Équipe"),
    (PERM_MANAGE_ROLES,             "Gérer les rôles personnalisés",        "Équipe"),
    # Menu
    (PERM_MANAGE_MENU,              "Gérer le menu (plats)",                "Menu"),
    # Commandes
    (PERM_VIEW_COMMANDES,           "Voir les commandes",                   "Commandes"),
    (PERM_MANAGE_COMMANDES,         "Servir et encaisser les commandes",    "Commandes"),
    # Cuisine
    (PERM_VIEW_CUISINE,             "Voir la file cuisine",                 "Cuisine"),
    (PERM_MANAGE_CUISINE,           "Marquer les commandes prêtes",         "Cuisine"),
    # Tables
    (PERM_MANAGE_TABLES,            "Gérer les tables et QR codes",         "Tables"),
    (PERM_VIEW_TABLES,              "Voir les tables",                      "Tables"),
    # Finance
    (PERM_MANAGE_CAISSE_COMPTABLE,  "Gérer la caisse du jour",              "Finance"),
    (PERM_VIEW_CAISSE_GLOBALE,      "Voir la caisse globale",               "Finance"),
    (PERM_MANAGE_CAISSE_GLOBALE,    "Fermer / ouvrir la caisse globale",    "Finance"),
    (PERM_VIEW_CAISSE_GENERALE,     "Voir la caisse générale",              "Finance"),
    (PERM_VIEW_REMISES,             "Voir ses remises",                     "Finance"),
    (PERM_MANAGE_REMISES,           "Valider les remises des serveurs",     "Finance"),
    # Restaurant
    (PERM_MANAGE_RESTAURANT,        "Modifier les paramètres du restaurant","Restaurant"),
]

# ── Permissions par rôle système ──────────────────────────────────────────────
# Utilisé par la data migration et le seed.

SYSTEM_ROLE_PERMISSIONS = {
    'Radmin': [
        PERM_MANAGE_EQUIPE, PERM_IMPERSONATE, PERM_MANAGE_ROLES,
        PERM_MANAGE_MENU,
        PERM_VIEW_COMMANDES, PERM_MANAGE_COMMANDES,
        PERM_VIEW_CUISINE, PERM_MANAGE_CUISINE,
        PERM_MANAGE_TABLES, PERM_VIEW_TABLES,
        PERM_VIEW_CAISSE_GLOBALE, PERM_MANAGE_CAISSE_GLOBALE,
        PERM_VIEW_CAISSE_GENERALE,
        PERM_VIEW_REMISES, PERM_MANAGE_REMISES,
        PERM_MANAGE_RESTAURANT,
    ],
    'Rmanager': [
        PERM_MANAGE_EQUIPE,
        PERM_MANAGE_MENU,
        PERM_VIEW_COMMANDES, PERM_MANAGE_COMMANDES,
        PERM_VIEW_CUISINE,
        PERM_VIEW_TABLES,
        PERM_VIEW_CAISSE_GLOBALE,
        PERM_VIEW_CAISSE_GENERALE,
    ],
    'Rserveur': [
        PERM_VIEW_COMMANDES, PERM_MANAGE_COMMANDES,
        PERM_VIEW_TABLES,
        PERM_VIEW_REMISES,
    ],
    'Rchef_cuisinier': [
        PERM_MANAGE_MENU,
        PERM_VIEW_COMMANDES,
        PERM_VIEW_CUISINE, PERM_MANAGE_CUISINE,
        PERM_VIEW_TABLES,
    ],
    'Rcuisinier': [
        PERM_VIEW_CUISINE, PERM_MANAGE_CUISINE,
    ],
    'Rcomptable': [
        PERM_MANAGE_CAISSE_COMPTABLE,
        PERM_VIEW_CAISSE_GLOBALE, PERM_MANAGE_CAISSE_GLOBALE,
        PERM_VIEW_CAISSE_GENERALE,
        PERM_VIEW_REMISES, PERM_MANAGE_REMISES,
        PERM_VIEW_COMMANDES,
    ],
}

# dashboard_type par rôle système
SYSTEM_ROLE_DASHBOARD = {
    'Radmin':          'admin',
    'Rmanager':        'admin',
    'Rserveur':        'serveur',
    'Rchef_cuisinier': 'cuisine',
    'Rcuisinier':      'cuisine',
    'Rcomptable':      'comptable',
}
