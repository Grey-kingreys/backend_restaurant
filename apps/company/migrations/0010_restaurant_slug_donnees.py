import re

from django.db import migrations


def remplir_slugs(apps, schema_editor):
    """Slug = valeur actuelle de get_slug() ; suffixe -2, -3 si collision."""
    Restaurant = apps.get_model("company", "Restaurant")
    utilises = set()
    for resto in Restaurant.objects.order_by("id"):
        base = re.sub(r"[^a-z0-9]", "", resto.nom.lower().replace(" ", ""))[:20] or "restaurant"
        candidat, n = base, 1
        while candidat in utilises:
            n += 1
            candidat = f"{base}-{n}"
        utilises.add(candidat)
        resto.slug = candidat
        resto.save(update_fields=["slug"])


class Migration(migrations.Migration):
    """Étape 2/3 : remplissage des slugs existants. Sans retour arrière utile
    (la colonne est supprimée par l'inverse de l'étape 1)."""

    dependencies = [
        ("company", "0009_restaurant_slug"),
    ]

    operations = [
        migrations.RunPython(remplir_slugs, migrations.RunPython.noop),
    ]
