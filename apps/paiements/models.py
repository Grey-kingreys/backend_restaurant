# apps/paiements/models.py
from django.db import models
from django.core.validators import MinValueValidator
from django.conf import settings
from decimal import Decimal


class Paiement(models.Model):
    """
    Enregistrement d'un paiement.
    Cree automatiquement quand une commande est marquee comme payee.
    Relation OneToOne avec Commande (une commande = un seul paiement).
    """

    commande = models.OneToOneField(
        'commandes.Commande',
        on_delete=models.CASCADE,
        related_name='paiement',
        verbose_name="Commande"
    )

    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Montant"
    )

    date_paiement = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de paiement"
    )

    class Meta:
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"
        ordering = ['-date_paiement']

    def __str__(self):
        return f"Paiement #{self.pk} - {self.montant} GNF"


class Caisse(models.Model):
    """
    Caisse du restaurant - SINGLETON (toujours pk=1).
    Ne jamais creer une deuxieme instance.
    Toujours utiliser Caisse.get_instance() pour y acceder.

    Le solde est mis a jour automatiquement :
    - +montant lors de chaque paiement
    - -montant lors de chaque depense
    """

    solde_actuel = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Solde actuel"
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Caisse"
        verbose_name_plural = "Caisses"

    def __str__(self):
        return f"Caisse - Solde: {self.solde_actuel} GNF"

    @classmethod
    def get_instance(cls):
        """
        Recupere ou cree l'instance unique de la caisse (pk=1).
        Toujours utiliser cette methode, jamais Caisse.objects.create().
        """
        caisse, created = cls.objects.get_or_create(pk=1)
        return caisse

    def peut_effectuer_depense(self, montant):
        """Verifie si le solde est suffisant pour une depense"""
        return self.solde_actuel >= montant


class Depense(models.Model):
    """
    Depense enregistree par le comptable.
    Le solde de la Caisse est debite automatiquement.
    Une depense ne peut pas etre supprimee si le solde devient negatif.
    """

    motif = models.CharField(
        max_length=255,
        verbose_name="Motif",
        help_text="Description de la depense (min 5 caracteres)"
    )

    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Montant"
    )

    date_depense = models.DateField(
        verbose_name="Date de la depense"
    )

    date_enregistrement = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date d'enregistrement"
    )

    enregistree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        limit_choices_to={'role': 'Rcomptable'},
        related_name='depenses_enregistrees',
        verbose_name="Enregistree par"
    )

    class Meta:
        verbose_name = "Depense"
        verbose_name_plural = "Depenses"
        ordering = ['-date_depense']

    def __str__(self):
        return f"{self.motif} - {self.montant} GNF"