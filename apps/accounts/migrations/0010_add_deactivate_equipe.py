"""
Ajoute la permission fine `deactivate_equipe` (activer / désactiver / supprimer
un membre) et l'attribue au rôle système Admin uniquement — pas au Manager.
"""
from django.db import migrations


PERM = ('deactivate_equipe', "Activer / désactiver / supprimer un membre", "Équipe")


def add_deactivate_equipe(apps, schema_editor):
    Permission = apps.get_model('accounts', 'Permission')
    RoleConfig = apps.get_model('accounts', 'RoleConfig')

    perm, _ = Permission.objects.get_or_create(
        code=PERM[0],
        defaults={'label': PERM[1], 'categorie': PERM[2]},
    )
    # Réservée à l'Admin (rôle système global, restaurant=None)
    for rc in RoleConfig.objects.filter(slug='Radmin', is_system=True):
        rc.permissions.add(perm)


def remove_deactivate_equipe(apps, schema_editor):
    Permission = apps.get_model('accounts', 'Permission')
    Permission.objects.filter(code=PERM[0]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_rclient_livraison'),
    ]

    operations = [
        migrations.RunPython(add_deactivate_equipe, reverse_code=remove_deactivate_equipe),
    ]
