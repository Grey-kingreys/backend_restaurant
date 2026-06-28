from django.db import migrations


def add_manage_tables_to_manager(apps, schema_editor):
    RoleConfig = apps.get_model('accounts', 'RoleConfig')
    Permission = apps.get_model('accounts', 'Permission')
    rc   = RoleConfig.objects.get(slug='Rmanager', is_system=True)
    perm = Permission.objects.get(code='manage_tables')
    rc.permissions.add(perm)


def remove_manage_tables_from_manager(apps, schema_editor):
    RoleConfig = apps.get_model('accounts', 'RoleConfig')
    Permission = apps.get_model('accounts', 'Permission')
    rc   = RoleConfig.objects.get(slug='Rmanager', is_system=True)
    perm = Permission.objects.get(code='manage_tables')
    rc.permissions.remove(perm)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_add_manage_restaurant_to_manager'),
    ]

    operations = [
        migrations.RunPython(
            add_manage_tables_to_manager,
            reverse_code=remove_manage_tables_from_manager,
        ),
    ]
