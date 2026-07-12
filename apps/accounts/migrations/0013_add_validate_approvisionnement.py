"""
Ajoute la permission `validate_approvisionnement` (valider / refuser les demandes
d'approvisionnement des comptables) et l'attribue aux roles Admin et Manager.
"""
from django.db import migrations


PERM = ('validate_approvisionnement', "Valider les demandes d'approvisionnement", "Finance")


def add_perm(apps, schema_editor):
    Permission = apps.get_model('accounts', 'Permission')
    RoleConfig = apps.get_model('accounts', 'RoleConfig')

    perm, _ = Permission.objects.get_or_create(
        code=PERM[0],
        defaults={'label': PERM[1], 'categorie': PERM[2]},
    )
    for slug in ('Radmin', 'Rmanager'):
        for rc in RoleConfig.objects.filter(slug=slug, is_system=True):
            rc.permissions.add(perm)


def remove_perm(apps, schema_editor):
    Permission = apps.get_model('accounts', 'Permission')
    Permission.objects.filter(code=PERM[0]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_add_livreur_role'),
    ]

    operations = [
        migrations.RunPython(add_perm, reverse_code=remove_perm),
    ]
