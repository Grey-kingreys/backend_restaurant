# apps/commandes/models.py
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings


class PanierItem(models.Model):
    """
    Panier en base de donnees.
    Un PanierItem = un plat dans le panier d'une table.
    Compatible mobile Flutter (pas de cookies/session).
    """

    table = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='panier_items',
        limit_choices_to={'role': 'Rtable'},
        verbose_name="Table"
    )

    plat = models.ForeignKey(
        'menu.Plat',
        on_delete=models.CASCADE,
        related_name='panier_items',
        verbose_name="Plat"
    )

    quantite = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        verbose_name="Quantite"
    )

    date_ajout = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date d'ajout"
    )

    class Meta:
        verbose_name = "Item du panier"
        verbose_name_plural = "Items du panier"
        unique_together = ['table', 'plat']

    def __str__(self):
        return f"Panier {self.table.login} - {self.plat.nom} x{self.quantite}"

    @property
    def sous_total(self):
        return self.quantite * self.plat.prix_unitaire


class Commande(models.Model):
    """
    Commande passee par une table.

    Workflow v2.0 :
    EN_ATTENTE -> PRETE (cuisinier) -> SERVIE (serveur) -> PAYEE

    Si aucun plat ne necessite_validation_cuisine :
    EN_ATTENTE -> SERVIE -> PAYEE (etape PRETE sautee)

    Visibilite :
    - Rtable    : uniquement les commandes de sa session QR active
    - Rserveur  : toutes les commandes
    - Rcuisinier: toutes les commandes en attente/prete
    - Radmin    : toutes les commandes
    """

    STATUS_CHOICES = [
        ('en_attente', 'En attente'),
        ('prete',      'Prete'),
        ('servie',     'Servie'),
        ('payee',      'Payee'),
    ]

    table = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='commandes',
        limit_choices_to={'role': 'Rtable'},
        verbose_name="Table"
    )

    # Lien avec la session QR - cle de l'amelioration
    # La table ne voit que les commandes de sa session active
    session = models.ForeignKey(
        'restaurant.TableSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='commandes_session',
        verbose_name="Session QR Code",
        help_text="Session lors de laquelle cette commande a ete passee"
    )

    montant_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name="Montant total"
    )

    statut = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='en_attente',
        verbose_name="Statut"
    )

    serveur_ayant_servi = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': 'Rserveur'},
        related_name='commandes_servies',
        verbose_name="Serveur ayant servi"
    )

    cuisinier_ayant_prepare = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': 'Rcuisinier'},
        related_name='commandes_preparees',
        verbose_name="Cuisinier ayant prepare"
    )

    date_paiement = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de paiement"
    )

    date_commande = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de commande"
    )

    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification"
    )

    class Meta:
        ordering = ['-date_commande']
        verbose_name = 'Commande'
        verbose_name_plural = 'Commandes'

    def __str__(self):
        return (
            f"Commande #{self.id} - "
            f"{self.table.login} - "
            f"{self.get_statut_display()}"
        )

    def est_modifiable(self):
        return self.statut == 'en_attente'

    def peut_etre_marquee_prete(self):
        return self.statut == 'en_attente'

    def peut_etre_servie(self):
        return self.statut in ('prete', 'en_attente')

    def peut_etre_payee(self):
        return self.statut == 'servie'

    def necessite_passage_cuisine(self):
        return self.items.filter(
            plat__necessite_validation_cuisine=True
        ).exists()


class CommandeItem(models.Model):
    """
    Ligne de commande : un plat dans une commande.
    Le prix_unitaire est capture au moment de la commande.
    """

    commande = models.ForeignKey(
        Commande,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Commande"
    )

    plat = models.ForeignKey(
        'menu.Plat',
        on_delete=models.PROTECT,
        related_name='commande_items',
        verbose_name="Plat"
    )

    quantite = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        verbose_name="Quantite"
    )

    prix_unitaire = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name="Prix unitaire"
    )

    class Meta:
        verbose_name = 'Ligne de commande'
        verbose_name_plural = 'Lignes de commande'
        unique_together = ['commande', 'plat']

    def __str__(self):
        return f"{self.plat.nom} x{self.quantite}"

    @property
    def sous_total(self):
        return self.quantite * self.prix_unitaire

    def save(self, *args, **kwargs):
        if not self.prix_unitaire:
            self.prix_unitaire = self.plat.prix_unitaire
        super().save(*args, **kwargs)