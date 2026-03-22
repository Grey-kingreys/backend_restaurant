# apps/menu/models.py
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class Plat(models.Model):
    """
    Modele representant un plat du menu.

    Nouveaute v2.0 :
    - necessite_validation_cuisine : si True, la commande passe par
      l'etape PRETE (cuisinier valide) avant d'etre SERVIE.
      Si False, le serveur peut servir directement depuis EN_ATTENTE.
    """

    CATEGORIE_CHOICES = [
        ('ENTREE',          'Entree'),
        ('PLAT',            'Plat principal'),
        ('DESSERT',         'Dessert'),
        ('BOISSON',         'Boisson'),
        ('ACCOMPAGNEMENT',  'Accompagnement'),
    ]

    nom = models.CharField(
        max_length=200,
        verbose_name="Nom du plat",
        help_text="Nom du plat (max 200 caracteres)"
    )

    description = models.TextField(
        verbose_name="Description",
        blank=True,
        null=True,
        help_text="Description detaillee du plat"
    )

    prix_unitaire = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Prix unitaire",
        help_text="Prix en GNF (Francs Guineens)"
    )

    image = models.ImageField(
        upload_to='plats/%Y/%m/',
        verbose_name="Image du plat",
        blank=True,
        null=True,
        help_text="Image du plat (formats acceptes: JPG, PNG)"
    )

    disponible = models.BooleanField(
        default=True,
        verbose_name="Disponible",
        help_text="Le plat est-il disponible a la commande ?"
    )

    categorie = models.CharField(
        max_length=20,
        choices=CATEGORIE_CHOICES,
        default='PLAT',
        verbose_name="Categorie"
    )

    # NOUVEAU v2.0
    necessite_validation_cuisine = models.BooleanField(
        default=False,
        verbose_name="Necessite validation cuisine",
        help_text=(
            "Si True : la commande doit passer par l'etape PRETE "
            "(un cuisinier valide la preparation) avant d'etre servie. "
            "Si False : le serveur peut servir directement."
        )
    )

    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de creation"
    )

    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Derniere modification"
    )

    class Meta:
        verbose_name = "Plat"
        verbose_name_plural = "Plats"
        ordering = ['categorie', 'nom']
        indexes = [
            models.Index(fields=['disponible', 'categorie']),
            models.Index(fields=['nom']),
        ]

    def __str__(self):
        statut = "OK" if self.disponible else "XX"
        return f"[{statut}] {self.nom} - {self.prix_unitaire} GNF"

    @property
    def prix_formate(self):
        """Retourne le prix formate avec separateur de milliers"""
        return f"{self.prix_unitaire:,.0f}".replace(',', ' ')

    def get_image_url(self):
        """Retourne l'URL de l'image ou None"""
        if self.image:
            return self.image.url
        return None


class PlatDisponibleManager(models.Manager):
    """Manager pour recuperer uniquement les plats disponibles"""
    def get_queryset(self):
        return super().get_queryset().filter(disponible=True)


# Ajouter le manager au modele
Plat.add_to_class('disponibles', PlatDisponibleManager())