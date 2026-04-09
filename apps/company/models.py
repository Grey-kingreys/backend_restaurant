# apps/company/models.py
from django.db import models
from django.core.validators import EmailValidator, RegexValidator


class Restaurant(models.Model):
    """
    Modele representant un tenant SaaS — un restaurant client.

    Cree par le Super Admin uniquement via l'interface d'administration.
    Tous les utilisateurs (sauf Rsuper_admin) ont une FK vers ce modele.

    IMPORTANT — Pas de FK vers accounts.User ici pour eviter la dependance
    circulaire avec accounts.User → company.Restaurant.
    La tracabilite du createur est geree au niveau de l'admin Django
    et des serializers (champ read-only createur dans les vues).

    Si is_active=False → tous les acces du restaurant sont bloques.
    """

    nom = models.CharField(
        max_length=200,
        verbose_name="Nom du restaurant"
    )

    email_admin = models.EmailField(
        validators=[EmailValidator()],
        verbose_name="Email de l'administrateur",
        help_text="Email de contact de l'admin du restaurant"
    )

    telephone = models.CharField(
        max_length=20,
        validators=[
            RegexValidator(
                regex=r'^\+?[0-9]{9,20}$',
                message="Format valide: +224XXXXXXXXX ou XXXXXXXXX (9-20 chiffres)"
            )
        ],
        verbose_name="Telephone"
    )

    adresse = models.TextField(
        blank=True,
        null=True,
        verbose_name="Adresse"
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Actif",
        help_text="Si False, tous les acces du restaurant sont bloques (suspension SaaS)"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de creation"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Derniere modification"
    )

    class Meta:
        verbose_name = "Restaurant"
        verbose_name_plural = "Restaurants"
        ordering = ['nom']

    def __str__(self):
        statut = "ACTIF" if self.is_active else "SUSPENDU"
        return f"{self.nom} [{statut}]"

    def suspendre(self):
        """Suspend le restaurant — bloque tous les acces"""
        self.is_active = False
        self.save(update_fields=['is_active', 'updated_at'])

    def reactiver(self):
        """Reactiver le restaurant"""
        self.is_active = True
        self.save(update_fields=['is_active', 'updated_at'])