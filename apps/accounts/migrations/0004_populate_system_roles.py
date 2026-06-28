"""
Data migration : crée les Permission + RoleConfig système
et assigne role_config à tous les users staff existants.
"""
from django.db import migrations


SYSTEM_ROLE_PERMISSIONS = {
    'Radmin': [
        'manage_equipe', 'impersonate', 'manage_roles',
        'manage_menu',
        'view_commandes', 'manage_commandes',
        'view_cuisine', 'manage_cuisine',
        'manage_tables', 'view_tables',
        'view_caisse_globale', 'manage_caisse_globale',
        'view_caisse_generale',
        'view_remises', 'manage_remises',
        'manage_restaurant',
    ],
    'Rmanager': [
        'manage_equipe',
        'manage_menu',
        'view_commandes', 'manage_commandes',
        'view_cuisine',
        'view_tables',
        'view_caisse_globale',
        'view_caisse_generale',
    ],
    'Rserveur': [
        'view_commandes', 'manage_commandes',
        'view_tables',
        'view_remises',
    ],
    'Rchef_cuisinier': [
        'manage_menu',
        'view_commandes',
        'view_cuisine', 'manage_cuisine',
        'view_tables',
    ],
    'Rcuisinier': [
        'view_cuisine', 'manage_cuisine',
    ],
    'Rcomptable': [
        'manage_caisse_comptable',
        'view_caisse_globale', 'manage_caisse_globale',
        'view_caisse_generale',
        'view_remises', 'manage_remises',
    ],
}

SYSTEM_ROLE_META = {
    'Radmin':          ('Administrateur',   'admin'),
    'Rmanager':        ('Manager',          'admin'),
    'Rserveur':        ('Serveur',          'serveur'),
    'Rchef_cuisinier': ('Chef Cuisinier',   'cuisine'),
    'Rcuisinier':      ('Cuisinier',        'cuisine'),
    'Rcomptable':      ('Comptable',        'comptable'),
}

ALL_PERMISSIONS = [
    ('manage_equipe',            "Gérer l'équipe",                       "Équipe"),
    ('impersonate',              "Simuler un membre",                    "Équipe"),
    ('manage_roles',             "Gérer les rôles personnalisés",        "Équipe"),
    ('manage_menu',              "Gérer le menu (plats)",                "Menu"),
    ('view_commandes',           "Voir les commandes",                   "Commandes"),
    ('manage_commandes',         "Servir et encaisser les commandes",    "Commandes"),
    ('view_cuisine',             "Voir la file cuisine",                 "Cuisine"),
    ('manage_cuisine',           "Marquer les commandes prêtes",         "Cuisine"),
    ('manage_tables',            "Gérer les tables et QR codes",         "Tables"),
    ('view_tables',              "Voir les tables",                      "Tables"),
    ('manage_caisse_comptable',  "Gérer la caisse du jour",              "Finance"),
    ('view_caisse_globale',      "Voir la caisse globale",               "Finance"),
    ('manage_caisse_globale',    "Fermer / ouvrir la caisse globale",    "Finance"),
    ('view_caisse_generale',     "Voir la caisse générale",              "Finance"),
    ('view_remises',             "Voir ses remises",                     "Finance"),
    ('manage_remises',           "Valider les remises des serveurs",     "Finance"),
    ('manage_restaurant',        "Modifier les paramètres du restaurant","Restaurant"),
]


def populate_permissions_and_roles(apps, schema_editor):
    Permission = apps.get_model('accounts', 'Permission')
    RoleConfig = apps.get_model('accounts', 'RoleConfig')
    User       = apps.get_model('accounts', 'User')

    # 1. Créer toutes les permissions
    perm_map = {}
    for code, label, categorie in ALL_PERMISSIONS:
        perm, _ = Permission.objects.get_or_create(
            code=code,
            defaults={'label': label, 'categorie': categorie},
        )
        perm_map[code] = perm

    # 2. Créer les RoleConfig système (restaurant=None)
    role_config_map = {}
    for slug, (nom, dashboard_type) in SYSTEM_ROLE_META.items():
        rc, _ = RoleConfig.objects.get_or_create(
            slug=slug,
            is_system=True,
            defaults={
                'nom': nom,
                'dashboard_type': dashboard_type,
                'restaurant': None,
            },
        )
        rc.permissions.set([perm_map[c] for c in SYSTEM_ROLE_PERMISSIONS[slug]])
        role_config_map[slug] = rc

    # 3. Assigner role_config aux users staff existants
    for slug, rc in role_config_map.items():
        User.objects.filter(role=slug).update(role_config=rc)


def depopulate_permissions_and_roles(apps, schema_editor):
    """Reverse : vider role_config sur tous les users, supprimer RoleConfig + Permission."""
    User       = apps.get_model('accounts', 'User')
    RoleConfig = apps.get_model('accounts', 'RoleConfig')
    Permission = apps.get_model('accounts', 'Permission')

    User.objects.all().update(role_config=None)
    RoleConfig.objects.filter(is_system=True).delete()
    Permission.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_add_permission_roleconfig_models'),
    ]

    operations = [
        migrations.RunPython(
            populate_permissions_and_roles,
            reverse_code=depopulate_permissions_and_roles,
        ),
    ]
