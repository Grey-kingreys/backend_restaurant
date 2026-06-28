"""
Data migration : ajoute manage_restaurant au RoleConfig système Rmanager.
Le manager doit pouvoir modifier les infos du restaurant sans dépendre de l'admin.
"""
from django.db import migrations


def add_manage_restaurant_to_manager(apps, schema_editor):
    RoleConfig = apps.get_model('accounts', 'RoleConfig')
    Permission = apps.get_model('accounts', 'Permission')
    try:
        rc   = RoleConfig.objects.get(slug='Rmanager', is_system=True)
        perm = Permission.objects.get(code='manage_restaurant')
        rc.permissions.add(perm)
    except (RoleConfig.DoesNotExist, Permission.DoesNotExist):
        pass


def remove_manage_restaurant_from_manager(apps, schema_editor):
    RoleConfig = apps.get_model('accounts', 'RoleConfig')
    Permission = apps.get_model('accounts', 'Permission')
    try:
        rc   = RoleConfig.objects.get(slug='Rmanager', is_system=True)
        perm = Permission.objects.get(code='manage_restaurant')
        rc.permissions.remove(perm)
    except (RoleConfig.DoesNotExist, Permission.DoesNotExist):
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_add_remises_to_manager'),
    ]

    operations = [
        migrations.RunPython(
            add_manage_restaurant_to_manager,
            reverse_code=remove_manage_restaurant_from_manager,
        ),
    ]
