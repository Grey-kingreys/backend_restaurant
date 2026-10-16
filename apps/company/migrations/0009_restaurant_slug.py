from django.db import migrations, models


class Migration(migrations.Migration):
    """Étape 1/3 : colonne slug nullable, sans unicité (remplie à l'étape 2)."""

    dependencies = [
        ("company", "0008_tirets_courts_libelles"),
    ]

    operations = [
        migrations.AddField(
            model_name="restaurant",
            name="slug",
            field=models.SlugField(max_length=30, null=True, editable=False, verbose_name="Slug public"),
        ),
    ]
