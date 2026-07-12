"""
Ajoute le rôle Livreur (Rlivreur) et les permissions de livraison.

- 3 permissions : view_livraisons, manage_livraisons, manage_livraison_links.
- Crée le rôle système Rlivreur (dashboard 'livreur') avec view/manage_livraisons.
- Étend Admin, Manager et Serveur avec les permissions livraison adaptées.
"""
from django.db import migrations


PERMS = [
    ('view_livraisons',         "Voir les livraisons à faire",          "Livraison"),
    ('manage_livraisons',       "Marquer en course / livrée",           "Livraison"),
    ('manage_livraison_links',  "Générer un lien / QR de livraison",    "Livraison"),
]

# Permissions ajoutées aux rôles système existants
ROLE_EXTRA = {
    'Radmin':   ['view_livraisons', 'manage_livraisons', 'manage_livraison_links'],
    'Rmanager': ['view_livraisons', 'manage_livraisons', 'manage_livraison_links'],
    'Rserveur': ['view_livraisons', 'manage_livraison_links'],
}

LIVREUR_PERMS = ['view_livraisons', 'manage_livraisons']


def add_livreur(apps, schema_editor):
    Permission = apps.get_model('accounts', 'Permission')
    RoleConfig = apps.get_model('accounts', 'RoleConfig')

    perm_map = {}
    for code, label, cat in PERMS:
        p, _ = Permission.objects.get_or_create(
            code=code, defaults={'label': label, 'categorie': cat},
        )
        perm_map[code] = p

    # Rôle système Livreur (global, restaurant=None)
    rc, _ = RoleConfig.objects.get_or_create(
        slug='Rlivreur', is_system=True,
        defaults={'nom': 'Livreur', 'dashboard_type': 'livreur', 'restaurant': None},
    )
    rc.dashboard_type = 'livreur'
    rc.save(update_fields=['dashboard_type'])
    rc.permissions.add(*[perm_map[c] for c in LIVREUR_PERMS])

    # Extension des rôles système existants
    for slug, codes in ROLE_EXTRA.items():
        for role in RoleConfig.objects.filter(slug=slug, is_system=True):
            role.permissions.add(*[perm_map[c] for c in codes])


def remove_livreur(apps, schema_editor):
    Permission = apps.get_model('accounts', 'Permission')
    RoleConfig = apps.get_model('accounts', 'RoleConfig')
    RoleConfig.objects.filter(slug='Rlivreur', is_system=True).delete()
    Permission.objects.filter(code__in=[c for c, _, _ in PERMS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_alter_roleconfig_dashboard_type_alter_user_role'),
    ]

    operations = [
        migrations.RunPython(add_livreur, reverse_code=remove_livreur),
    ]
