# apps/paiements/models.py
from django.db import models
from django.core.validators import MinValueValidator
from django.conf import settings
from django.utils import timezone
from decimal import Decimal


# ─────────────────────────────────────────────────────────────────────────────
# CAISSE GENERALE
# ─────────────────────────────────────────────────────────────────────────────

class CaisseGenerale(models.Model):
    """
    Caisse permanente du restaurant — OneToOne avec Restaurant.
    Ne se ferme JAMAIS.
    Creee automatiquement lors de la configuration du restaurant.
    Visible uniquement par Admin et Manager.

    Alimentee par :
    - Fermeture de la Caisse Globale du jour
    - Fermeture de chaque Caisse Comptable
    """

    restaurant = models.OneToOneField(
        'company.Restaurant',
        on_delete=models.CASCADE,
        related_name='caisse_generale',
        verbose_name="Restaurant"
    )

    solde = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Solde actuel (GNF)"
    )

    # Solde initial saisi par l'Admin a la configuration (peut etre 0)
    solde_initial = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Solde initial"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Caisse Generale"
        verbose_name_plural = "Caisses Generales"

    def __str__(self):
        return f"Caisse Generale — {self.restaurant.nom} — {self.solde} GNF"

    def crediter(self, montant):
        """Ajoute un montant au solde"""
        self.solde += Decimal(str(montant))
        self.save(update_fields=['solde', 'updated_at'])

    def debiter(self, montant):
        """Retire un montant du solde — verifie la solvabilite avant"""
        if not self.peut_debiter(montant):
            raise ValueError(f"Solde insuffisant: {self.solde} GNF < {montant} GNF")
        self.solde -= Decimal(str(montant))
        self.save(update_fields=['solde', 'updated_at'])

    def peut_debiter(self, montant):
        return self.solde >= Decimal(str(montant))


# ─────────────────────────────────────────────────────────────────────────────
# CAISSE GLOBALE
# ─────────────────────────────────────────────────────────────────────────────

class CaisseGlobale(models.Model):
    """
    Caisse journaliere du restaurant — centralise les paiements des tables.
    Ouverte automatiquement chaque jour a 05h00 par Celery Beat.
    Fermee manuellement par le comptable designe (ou tout autre en son absence).
    Une seule active a la fois par restaurant.

    A la fermeture : solde transfete dans la Caisse Generale.
    Une fois fermee : IMMUABLE — lecture seule.
    """

    restaurant = models.ForeignKey(
        'company.Restaurant',
        on_delete=models.CASCADE,
        related_name='caisses_globales',
        verbose_name="Restaurant"
    )

    date_ouverture = models.DateField(
        verbose_name="Date d'ouverture",
        help_text="Automatiquement a 05h00 chaque jour"
    )

    solde = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Solde (GNF)"
    )

    is_closed = models.BooleanField(
        default=False,
        verbose_name="Fermee"
    )

    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de fermeture"
    )

    fermee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='caisses_globales_fermees',
        verbose_name="Fermee par"
    )

    # Motif si ecart entre solde virtuel et montant physique a la fermeture
    motif_ecart = models.TextField(
        blank=True,
        null=True,
        verbose_name="Motif d'ecart",
        help_text="Obligatoire si ecart entre solde virtuel et montant physique"
    )

    montant_physique_fermeture = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Montant physique a la fermeture"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Caisse Globale"
        verbose_name_plural = "Caisses Globales"
        ordering = ['-date_ouverture']

    def __str__(self):
        statut = "FERMEE" if self.is_closed else "OUVERTE"
        return f"Caisse Globale {self.date_ouverture} — {self.restaurant.nom} [{statut}]"

    def crediter(self, montant):
        """Credite la caisse — appele lors de chaque validation de remise serveur"""
        if self.is_closed:
            raise ValueError("Impossible de crediter une caisse fermee")
        self.solde += Decimal(str(montant))
        self.save(update_fields=['solde', 'updated_at'])

    def fermer(self, fermee_par, montant_physique, motif_ecart=None):
        """
        Ferme la caisse — IRREVERSIBLE.
        Transfete le solde dans la Caisse Generale.
        """
        if self.is_closed:
            raise ValueError("Cette caisse est deja fermee")

        ecart = abs(self.solde - Decimal(str(montant_physique)))
        if ecart > 0 and not motif_ecart:
            raise ValueError("Le motif d'ecart est obligatoire si le montant physique differe du solde")

        self.is_closed = True
        self.closed_at = timezone.now()
        self.fermee_par = fermee_par
        self.montant_physique_fermeture = Decimal(str(montant_physique))
        self.motif_ecart = motif_ecart
        self.save()

        # Transfert vers la Caisse Generale
        caisse_generale = self.restaurant.caisse_generale
        caisse_generale.crediter(self.solde)

        return self


# ─────────────────────────────────────────────────────────────────────────────
# CAISSE COMPTABLE
# ─────────────────────────────────────────────────────────────────────────────

class CaisseComptable(models.Model):
    """
    Caisse personnelle d'un comptable — session de travail.
    Un comptable ne peut avoir qu'une seule caisse ouverte a la fois.
    Ouverte manuellement par le comptable en debut de journee.

    Flux :
    - Approvisionnee depuis la Caisse Generale
    - Debitee pour chaque depense enregistree
    - A la fermeture : solde restant transfete dans la Caisse Generale
    """

    restaurant = models.ForeignKey(
        'company.Restaurant',
        on_delete=models.CASCADE,
        related_name='caisses_comptables',
        verbose_name="Restaurant"
    )

    comptable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'Rcomptable'},
        related_name='caisses_comptables',
        verbose_name="Comptable"
    )

    solde = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Solde (GNF)"
    )

    is_closed = models.BooleanField(
        default=False,
        verbose_name="Fermee"
    )

    opened_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date d'ouverture"
    )

    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de fermeture"
    )

    motif_ecart = models.TextField(
        blank=True,
        null=True,
        verbose_name="Motif d'ecart a la fermeture"
    )

    montant_physique_fermeture = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Montant physique a la fermeture"
    )

    class Meta:
        verbose_name = "Caisse Comptable"
        verbose_name_plural = "Caisses Comptables"
        ordering = ['-opened_at']

    def __str__(self):
        statut = "FERMEE" if self.is_closed else "OUVERTE"
        return f"Caisse {self.comptable.nom_complet} — {self.opened_at.date()} [{statut}]"

    def peut_effectuer_depense(self, montant):
        """Verifie si le solde est suffisant pour une depense"""
        return self.solde >= Decimal(str(montant))

    def debiter(self, montant):
        """Debite pour une depense"""
        if self.is_closed:
            raise ValueError("Impossible de debiter une caisse fermee")
        if not self.peut_effectuer_depense(montant):
            raise ValueError(f"Solde insuffisant: {self.solde} GNF")
        self.solde -= Decimal(str(montant))
        self.save(update_fields=['solde'])

    def crediter(self, montant):
        """Credite depuis la Caisse Generale (approvisionnement)"""
        if self.is_closed:
            raise ValueError("Impossible de crediter une caisse fermee")
        self.solde += Decimal(str(montant))
        self.save(update_fields=['solde'])

    def fermer(self, montant_physique, motif_ecart=None):
        """
        Ferme la caisse — IRREVERSIBLE.
        Transfete le solde restant dans la Caisse Generale.
        """
        if self.is_closed:
            raise ValueError("Cette caisse est deja fermee")

        ecart = abs(self.solde - Decimal(str(montant_physique)))
        if ecart > 0 and not motif_ecart:
            raise ValueError("Le motif d'ecart est obligatoire")

        self.is_closed = True
        self.closed_at = timezone.now()
        self.montant_physique_fermeture = Decimal(str(montant_physique))
        self.motif_ecart = motif_ecart
        self.save()

        # Transfert solde restant vers Caisse Generale
        caisse_generale = self.restaurant.caisse_generale
        caisse_generale.crediter(self.solde)

        return self


# ─────────────────────────────────────────────────────────────────────────────
# MOUVEMENT CAISSE (trace tous les mouvements de la Caisse Comptable)
# ─────────────────────────────────────────────────────────────────────────────

class MouvementCaisse(models.Model):
    """
    Trace chaque mouvement de la Caisse Comptable.
    Non modifiable apres creation — audit trail complet.
    """

    TYPE_CHOICES = [
        ('approvisionnement', 'Approvisionnement'),
        ('depense',           'Depense'),
    ]

    caisse_comptable = models.ForeignKey(
        CaisseComptable,
        on_delete=models.CASCADE,
        related_name='mouvements',
        verbose_name="Caisse comptable"
    )

    type_mouvement = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        verbose_name="Type de mouvement"
    )

    montant = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Montant (GNF)"
    )

    motif = models.CharField(
        max_length=255,
        verbose_name="Motif",
        help_text="Description du mouvement (min 5 caracteres)"
    )

    effectue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='mouvements_caisse',
        verbose_name="Effectue par"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date"
    )

    class Meta:
        verbose_name = "Mouvement de caisse"
        verbose_name_plural = "Mouvements de caisse"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_type_mouvement_display()} — {self.montant} GNF — {self.created_at.date()}"


# ─────────────────────────────────────────────────────────────────────────────
# REMISE SERVEUR
# ─────────────────────────────────────────────────────────────────────────────

class RemiseServeur(models.Model):
    """
    Validation physique d'un paiement par un comptable.

    Workflow :
    1. Serveur valide le paiement → commande PAYEE
    2. Serveur remet l'argent physique au comptable
    3. Comptable saisit le montant recu
    4a. Si correct → Caisse Globale creditee
    4b. Si ecart → motif_ecart obligatoire puis validation
    """

    caisse_globale = models.ForeignKey(
        CaisseGlobale,
        on_delete=models.CASCADE,
        related_name='remises',
        verbose_name="Caisse Globale"
    )

    paiement = models.OneToOneField(
        'Paiement',
        on_delete=models.CASCADE,
        related_name='remise',
        verbose_name="Paiement associe"
    )

    montant_virtuel = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Montant virtuel (attendu)"
    )

    montant_physique = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Montant physique (recu)"
    )

    motif_ecart = models.TextField(
        blank=True,
        null=True,
        verbose_name="Motif de l'ecart",
        help_text="Obligatoire si montant physique != montant virtuel"
    )

    valide = models.BooleanField(
        default=False,
        verbose_name="Validee par comptable"
    )

    validee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': 'Rcomptable'},
        related_name='remises_validees',
        verbose_name="Validee par"
    )

    serveur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='remises_effectuees',
        verbose_name="Serveur"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Remise serveur"
        verbose_name_plural = "Remises serveurs"
        ordering = ['-created_at']

    def __str__(self):
        statut = "VALIDEE" if self.valide else "EN ATTENTE"
        return f"Remise {self.montant_virtuel} GNF [{statut}]"

    @property
    def ecart(self):
        """Calcule l'ecart entre montant virtuel et physique"""
        if self.montant_physique is None:
            return None
        return self.montant_physique - self.montant_virtuel


# ─────────────────────────────────────────────────────────────────────────────
# PAIEMENT (inchange — OneToOne avec Commande)
# ─────────────────────────────────────────────────────────────────────────────

class Paiement(models.Model):
    """
    Enregistrement d'un paiement.
    Cree automatiquement quand une commande est marquee comme PAYEE.
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
        return f"Paiement #{self.pk} — {self.montant} GNF"


# ─────────────────────────────────────────────────────────────────────────────
# DEPENSE (attachee a la Caisse Comptable — plus a la Caisse singleton)
# ─────────────────────────────────────────────────────────────────────────────

class Depense(models.Model):
    """
    Depense enregistree par un comptable depuis sa Caisse Comptable.
    Impossible si le solde de la Caisse Comptable est insuffisant.
    Non modifiable apres creation.
    """

    caisse_comptable = models.ForeignKey(
        CaisseComptable,
        on_delete=models.CASCADE,
        related_name='depenses',
        verbose_name="Caisse comptable"
    )

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