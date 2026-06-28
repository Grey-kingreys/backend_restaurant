"""
Data migration : ajoute PERM_VIEW_COMMANDES au RoleConfig système Rcomptable.
Le comptable a besoin de voir les commandes pour accéder aux reçus PDF.
"""
from django.db import migrations


def add_view_commandes_to_comptable(apps, schema_editor):
    RoleConfig = apps.get_model('accounts', 'RoleConfig')
    Permission = apps.get_model('accounts', 'Permission')
    try:
        rc  = RoleConfig.objects.get(slug='Rcomptable', is_system=True)
        perm = Permission.objects.get(code='view_commandes')
        rc.permissions.add(perm)
    except (RoleConfig.DoesNotExist, Permission.DoesNotExist):
        pass


def remove_view_commandes_from_comptable(apps, schema_editor):
    RoleConfig = apps.get_model('accounts', 'RoleConfig')
    Permission = apps.get_model('accounts', 'Permission')
    try:
        rc   = RoleConfig.objects.get(slug='Rcomptable', is_system=True)
        perm = Permission.objects.get(code='view_commandes')
        rc.permissions.remove(perm)
    except (RoleConfig.DoesNotExist, Permission.DoesNotExist):
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_populate_system_roles'),
    ]

    operations = [
        migrations.RunPython(
            add_view_commandes_to_comptable,
            reverse_code=remove_view_commandes_from_comptable,
        ),
    ]
