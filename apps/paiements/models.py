# apps/paiements/models.py
from django.db import models, transaction
from django.core.validators import MinValueValidator
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

from .exceptions import ErreurMetier


# ─────────────────────────────────────────────────────────────────────────────
# CAISSE GENERALE
# ─────────────────────────────────────────────────────────────────────────────

class CaisseGenerale(models.Model):
    """
    Caisse permanente du restaurant - OneToOne avec Restaurant.
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

    # Renseignee au premier appel de /caisse-generale/init/. Permet de distinguer
    # « coffre jamais configure » de « configure volontairement a 0 GNF » - un
    # solde_initial a 0 ne suffit pas, c'est aussi la valeur par defaut.
    date_initialisation = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Date d'initialisation du solde",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Caisse Generale"
        verbose_name_plural = "Caisses Generales"

    def __str__(self):
        return f"Caisse Generale - {self.restaurant.nom} - {self.solde} GNF"

    @classmethod
    def pour_restaurant(cls, restaurant):
        """Retourne le coffre du restaurant - le cree a 0 GNF s'il n'existe pas.

        Tout restaurant possede un coffre : seul son solde initial est saisi par
        l'Admin via `/caisse-generale/init/`. Les restaurants crees par
        l'onboarding n'en avaient aucun, et chaque transfert (approvisionnement,
        fermeture de caisse) levait `RelatedObjectDoesNotExist` -> HTTP 500.
        """
        caisse, _ = cls.objects.get_or_create(restaurant=restaurant)
        return caisse

    def crediter(self, montant):
        """Ajoute un montant au solde - increment atomique via F() (anti-race)."""
        montant = Decimal(str(montant))
        type(self).objects.filter(pk=self.pk).update(
            solde=models.F('solde') + montant, updated_at=timezone.now()
        )
        self.refresh_from_db(fields=['solde', 'updated_at'])

    def debiter(self, montant):
        """Retire un montant - decrement conditionnel atomique (anti-race)."""
        montant = Decimal(str(montant))
        updated = type(self).objects.filter(pk=self.pk, solde__gte=montant).update(
            solde=models.F('solde') - montant, updated_at=timezone.now()
        )
        if not updated:
            self.refresh_from_db(fields=['solde'])
            raise ValueError(f"Solde insuffisant: {self.solde} GNF < {montant} GNF")
        self.refresh_from_db(fields=['solde', 'updated_at'])

    def peut_debiter(self, montant):
        return self.solde >= Decimal(str(montant))


# ─────────────────────────────────────────────────────────────────────────────
# CAISSE GLOBALE
# ─────────────────────────────────────────────────────────────────────────────

class CaisseGlobale(models.Model):
    """
    Caisse journaliere du restaurant - centralise les paiements des tables.
    Ouverte automatiquement chaque jour a 05h00 par Celery Beat.
    Fermee manuellement par le comptable designe (ou tout autre en son absence).
    Une seule active a la fois par restaurant.

    A la fermeture : solde transfete dans la Caisse Generale.
    Une fois fermee : IMMUABLE - lecture seule.
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
        return f"Caisse Globale {self.date_ouverture} - {self.restaurant.nom} [{statut}]"

    def crediter(self, montant):
        """Credite la caisse (increment atomique) - refuse si fermee."""
        montant = Decimal(str(montant))
        updated = type(self).objects.filter(pk=self.pk, is_closed=False).update(
            solde=models.F('solde') + montant, updated_at=timezone.now()
        )
        if not updated:
            raise ValueError("Impossible de crediter une caisse fermee")
        self.refresh_from_db(fields=['solde', 'updated_at'])

    @transaction.atomic
    def fermer(self, fermee_par, montant_physique, motif_ecart=None):
        """
        Ferme la caisse - IRREVERSIBLE.
        Transfete le solde dans la Caisse Generale.
        Verrou pessimiste : empeche double fermeture / credit concurrent.
        """
        locked = type(self).objects.select_for_update().get(pk=self.pk)
        if locked.is_closed:
            raise ValueError("Cette caisse est deja fermee")
        self.solde = locked.solde  # solde fige sous verrou

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
        caisse_generale = CaisseGenerale.pour_restaurant(self.restaurant)
        caisse_generale.crediter(self.solde)

        return self


# ─────────────────────────────────────────────────────────────────────────────
# CAISSE COMPTABLE
# ─────────────────────────────────────────────────────────────────────────────

class CaisseComptable(models.Model):
    """
    Caisse personnelle d'un comptable - session de travail.
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
        return f"Caisse {self.comptable.nom_complet} - {self.opened_at.date()} [{statut}]"

    def peut_effectuer_depense(self, montant):
        """Verifie si le solde est suffisant pour une depense"""
        return self.solde >= Decimal(str(montant))

    def debiter(self, montant):
        """Debite pour une depense - decrement conditionnel atomique (anti-race)."""
        montant = Decimal(str(montant))
        updated = type(self).objects.filter(
            pk=self.pk, is_closed=False, solde__gte=montant
        ).update(solde=models.F('solde') - montant)
        if not updated:
            self.refresh_from_db(fields=['solde', 'is_closed'])
            if self.is_closed:
                raise ValueError("Impossible de debiter une caisse fermee")
            raise ValueError(f"Solde insuffisant: {self.solde} GNF")
        self.refresh_from_db(fields=['solde'])

    def crediter(self, montant):
        """Credite depuis la Caisse Generale (increment atomique)."""
        montant = Decimal(str(montant))
        updated = type(self).objects.filter(pk=self.pk, is_closed=False).update(
            solde=models.F('solde') + montant
        )
        if not updated:
            raise ValueError("Impossible de crediter une caisse fermee")
        self.refresh_from_db(fields=['solde'])

    @transaction.atomic
    def fermer(self, montant_physique, motif_ecart=None, fermee_par=None):
        """
        Ferme la caisse - IRREVERSIBLE.
        Transfere le MONTANT PHYSIQUE reellement compte dans la Caisse Generale
        (le coffre reflete le cash reel) et trace l'ecart eventuel
        (physique - virtuel) comme perte/gain.
        Verrou pessimiste : empeche double fermeture / mouvement concurrent.
        """
        locked = type(self).objects.select_for_update().get(pk=self.pk)
        if locked.is_closed:
            raise ValueError("Cette caisse est deja fermee")
        self.solde = locked.solde  # solde fige sous verrou

        montant_physique = Decimal(str(montant_physique))
        solde_virtuel = self.solde
        ecart = montant_physique - solde_virtuel  # >0 excedent, <0 manquant
        if ecart != 0 and not motif_ecart:
            raise ValueError("Le motif d'ecart est obligatoire")

        self.is_closed = True
        self.closed_at = timezone.now()
        self.montant_physique_fermeture = montant_physique
        self.motif_ecart = motif_ecart
        self.save()

        # Transfert du cash reellement compte vers la Caisse Generale
        caisse_generale = CaisseGenerale.pour_restaurant(self.restaurant)
        if montant_physique > 0:
            caisse_generale.crediter(montant_physique)
            MouvementCaisse.objects.create(
                caisse_comptable=self,
                type_mouvement='fermeture',
                montant=montant_physique,
                motif="Transfert du montant physique vers la Caisse Generale a la fermeture",
                effectue_par=fermee_par,
            )

        # Ecart (physique - virtuel) trace comme perte/gain
        if ecart != 0:
            sens = "Excedent" if ecart > 0 else "Manquant"
            MouvementCaisse.objects.create(
                caisse_comptable=self,
                type_mouvement='ecart',
                montant=abs(ecart),
                motif=f"{sens} a la fermeture (solde virtuel {solde_virtuel:.0f} GNF) : {motif_ecart or '-'}",
                effectue_par=fermee_par,
            )

        return self


# ─────────────────────────────────────────────────────────────────────────────
# MOUVEMENT CAISSE (trace tous les mouvements de la Caisse Comptable)
# ─────────────────────────────────────────────────────────────────────────────

class MouvementCaisse(models.Model):
    """
    Trace chaque mouvement de la Caisse Comptable.
    Non modifiable apres creation - audit trail complet.
    """

    TYPE_CHOICES = [
        ('approvisionnement', 'Approvisionnement'),
        ('depense',           'Depense'),
        ('fermeture',         'Fermeture (transfert vers Caisse Generale)'),
        ('ecart',             'Ecart de caisse'),
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
        return f"{self.get_type_mouvement_display()} - {self.montant} GNF - {self.created_at.date()}"


# ─────────────────────────────────────────────────────────────────────────────
# DEMANDE D'APPROVISIONNEMENT (validation Admin / Manager)
# ─────────────────────────────────────────────────────────────────────────────

class DemandeApprovisionnement(models.Model):
    """
    Demande d'approvisionnement d'une Caisse Comptable depuis la Caisse Generale.
    Le comptable cree une demande ; un Admin ou Manager la valide ou la refuse.
    L'argent ne bouge QU'A la validation (separation des taches).
    """
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('approuvee',  'Approuvee'),
        ('refusee',    'Refusee'),
    ]

    restaurant = models.ForeignKey(
        'company.Restaurant', on_delete=models.CASCADE,
        related_name='demandes_appro', verbose_name="Restaurant",
    )
    caisse_comptable = models.ForeignKey(
        CaisseComptable, on_delete=models.CASCADE,
        related_name='demandes_appro', verbose_name="Caisse comptable",
    )
    montant = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Montant demande (GNF)",
    )
    motif = models.CharField(max_length=255, verbose_name="Motif de la demande")
    statut = models.CharField(
        max_length=12, choices=STATUT_CHOICES, default='en_attente',
        verbose_name="Statut",
    )
    demande_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='demandes_appro_creees', verbose_name="Demande par",
    )
    validee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='demandes_appro_validees', verbose_name="Validee/refusee par",
    )
    motif_refus = models.TextField(null=True, blank=True, verbose_name="Motif du refus")
    created_at = models.DateTimeField(auto_now_add=True)
    validated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Demande d'approvisionnement"
        verbose_name_plural = "Demandes d'approvisionnement"
        ordering = ['-created_at']

    def __str__(self):
        return f"Demande appro {self.montant} GNF - {self.get_statut_display()}"

    @transaction.atomic
    def approuver(self, validee_par):
        """Valide la demande : l'argent bouge ENFIN (coffre → caisse comptable)."""
        if self.statut != 'en_attente':
            raise ErreurMetier("Cette demande a deja ete traitee.")
        caisse = self.caisse_comptable
        if caisse.is_closed:
            raise ErreurMetier("La caisse comptable est fermee.")
        caisse_generale = CaisseGenerale.pour_restaurant(self.restaurant)
        if caisse_generale.solde <= 0:
            raise ErreurMetier(
                "La Caisse Generale est vide (0 GNF) : un Admin doit d'abord "
                "l'initialiser ou la crediter avant de valider un approvisionnement."
            )
        if not caisse_generale.peut_debiter(self.montant):
            raise ErreurMetier(
                f"Solde insuffisant dans la Caisse Generale : {caisse_generale.solde:.0f} GNF disponibles."
            )
        caisse_generale.debiter(self.montant)
        caisse.crediter(self.montant)
        MouvementCaisse.objects.create(
            caisse_comptable=caisse,
            type_mouvement='approvisionnement',
            montant=self.montant,
            motif=self.motif,
            effectue_par=validee_par,
        )
        self.statut = 'approuvee'
        self.validee_par = validee_par
        self.validated_at = timezone.now()
        self.save(update_fields=['statut', 'validee_par', 'validated_at'])
        return self

    def refuser(self, validee_par, motif_refus):
        """Refuse la demande : aucun mouvement d'argent."""
        if self.statut != 'en_attente':
            raise ErreurMetier("Cette demande a deja ete traitee.")
        self.statut = 'refusee'
        self.validee_par = validee_par
        self.motif_refus = motif_refus
        self.validated_at = timezone.now()
        self.save(update_fields=['statut', 'validee_par', 'motif_refus', 'validated_at'])
        return self


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
# PAIEMENT (inchange - OneToOne avec Commande)
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
        return f"Paiement #{self.pk} - {self.montant} GNF"


# ─────────────────────────────────────────────────────────────────────────────
# DEPENSE (attachee a la Caisse Comptable - plus a la Caisse singleton)
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