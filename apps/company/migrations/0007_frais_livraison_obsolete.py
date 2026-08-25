from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Les frais de livraison varient avec la distance : ils ne sont plus factures
    dans la commande et se conviennent directement avec le livreur.

    La colonne est conservee (aucune perte des montants deja saisis), seule sa
    documentation change pour signaler qu'elle n'est plus lue par l'application.
    """

    dependencies = [
        ('company', '0006_restaurant_livraison_lien_autorise_paiement'),
    ]

    operations = [
        migrations.AlterField(
            model_name='restaurant',
            name='frais_livraison',
            field=models.DecimalField(
                blank=True,
                decimal_places=0,
                help_text="Obsolete : les frais sont convenus avec le livreur selon la distance.",
                max_digits=10,
                null=True,
                verbose_name='Frais de livraison (GNF) — obsolete',
            ),
        ),
    ]
