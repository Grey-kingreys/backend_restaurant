"""
Data migration : ajoute view_remises au RoleConfig système Rmanager.
Le manager doit pouvoir visualiser les remises pour le suivi financier.
"""
from django.db import migrations


def add_view_remises_to_manager(apps, schema_editor):
    RoleConfig = apps.get_model('accounts', 'RoleConfig')
    Permission = apps.get_model('accounts', 'Permission')
    try:
        rc   = RoleConfig.objects.get(slug='Rmanager', is_system=True)
        perm = Permission.objects.get(code='view_remises')
        rc.permissions.add(perm)
    except (RoleConfig.DoesNotExist, Permission.DoesNotExist):
        pass


def remove_view_remises_from_manager(apps, schema_editor):
    RoleConfig = apps.get_model('accounts', 'RoleConfig')
    Permission = apps.get_model('accounts', 'Permission')
    try:
        rc   = RoleConfig.objects.get(slug='Rmanager', is_system=True)
        perm = Permission.objects.get(code='view_remises')
        rc.permissions.remove(perm)
    except (RoleConfig.DoesNotExist, Permission.DoesNotExist):
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_add_view_commandes_to_comptable'),
    ]

    operations = [
        migrations.RunPython(
            add_view_remises_to_manager,
            reverse_code=remove_view_remises_from_manager,
        ),
    ]
