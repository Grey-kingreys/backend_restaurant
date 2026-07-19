"""
Data migration : ne garde qu'une session active par table.

Corrige les données où plusieurs TableSession(est_active=True) coexistaient
pour une même table (empilement d'anciens scans QR). Sans ça, les vues qui
faisaient `.get(table=..., est_active=True)` levaient MultipleObjectsReturned.
La logique de création (TableSession.ouvrir_pour) empêche désormais la récidive.
"""
from django.db import migrations
from django.db.models import Count, Max


def dedupe_sessions_actives(apps, schema_editor):
    TableSession = apps.get_model('restaurant', 'TableSession')
    doublons = (
        TableSession.objects.filter(est_active=True)
        .values('table')
        .annotate(n=Count('id'), derniere=Max('id'))
        .filter(n__gt=1)
    )
    for row in doublons:
        TableSession.objects.filter(
            table_id=row['table'], est_active=True
        ).exclude(id=row['derniere']).update(est_active=False)


def noop_reverse(apps, schema_editor):
    # Irréversible : on ne peut pas savoir quelles sessions réactiver.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('restaurant', '0004_reservation_duree_minutes_alter_reservation_statut_and_more'),
    ]

    operations = [
        migrations.RunPython(dedupe_sessions_actives, reverse_code=noop_reverse),
    ]
