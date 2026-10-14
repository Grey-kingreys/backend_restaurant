from django.db import migrations, models


class Migration(migrations.Migration):
    """Étape 3/3 : slug obligatoire et unique."""

    dependencies = [
        ("company", "0010_restaurant_slug_donnees"),
    ]

    operations = [
        migrations.AlterField(
            model_name="restaurant",
            name="slug",
            field=models.SlugField(max_length=30, unique=True, editable=False, verbose_name="Slug public"),
        ),
    ]
