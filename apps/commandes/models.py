# apps/commandes/models.py
import secrets
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
from django.utils import timezone


class PanierItem(models.Model):
    """
    Panier en base de donnees.
    Un PanierItem = un plat dans le panier d'une table.
    Isolation SaaS : heritee via table (User → restaurant).
    unique_together [table, plat] : un seul item par plat dans le panier.
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
        return f"Panier {self.table.login} — {self.plat.nom} x{self.quantite}"

    @property
    def sous_total(self):
        return self.quantite * self.plat.prix_unitaire


class Commande(models.Model):
    """
    Commande passee par une table.

    Isolation SaaS : FK restaurant directe pour filtrage efficace.
    La FK table (User) pointe deja vers le restaurant, mais on garde
    restaurant en direct pour les QuerySets sans jointure supplementaire.

    Workflow v2 :
    EN_ATTENTE → PRETE (cuisinier) → SERVIE (serveur) → PAYEE
    Si aucun plat necessite_validation_cuisine : EN_ATTENTE → SERVIE → PAYEE
    """

    STATUS_CHOICES = [
        ('en_attente',   'En attente'),
        ('prete',        'Prete'),
        ('en_livraison', 'En livraison'),
        ('servie',       'Servie / Livree'),
        ('payee',        'Payee'),
        ('annulee',      'Annulee'),
    ]

    TYPE_CHOICES = [
        ('sur_table',  'Sur table (QR)'),
        ('livraison',  'Livraison a domicile'),
        ('emporter',   'A emporter'),
    ]

    MODE_PAIEMENT_CHOICES = [
        ('livraison',    'Paiement a la livraison'),
        ('orange_money', 'Orange Money'),
        ('mtn',          'MTN Mobile Money'),
        ('carte',        'Carte bancaire'),
        ('paydunya',     'PayDunya'),
    ]

    # ── Isolation SaaS ────────────────────────────────────────────────────
    restaurant = models.ForeignKey(
        'company.Restaurant',
        on_delete=models.CASCADE,
        related_name='commandes',
        verbose_name="Restaurant"
    )

    # ── Champs metier ─────────────────────────────────────────────────────
    type_commande = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default='sur_table',
        verbose_name="Type de commande"
    )

    table = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='commandes',
        limit_choices_to={'role__in': ['Rtable', 'Rclient']},
        verbose_name="Table / Client"
    )

    # ── Infos client (commandes livraison / emporter) ─────────────────────
    client_nom = models.CharField(
        max_length=150, null=True, blank=True, verbose_name="Nom du client"
    )
    client_telephone = models.CharField(
        max_length=20, null=True, blank=True, verbose_name="Telephone du client"
    )
    client_adresse_livraison = models.TextField(
        null=True, blank=True, verbose_name="Adresse de livraison"
    )
    client_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name="Latitude livraison"
    )
    client_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name="Longitude livraison"
    )
    mode_paiement = models.CharField(
        max_length=20,
        choices=MODE_PAIEMENT_CHOICES,
        null=True, blank=True,
        verbose_name="Mode de paiement"
    )
    cle_suivi = models.CharField(
        max_length=32, unique=True, null=True, blank=True,
        verbose_name="Cle de suivi publique"
    )

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

    # ── Annulation ────────────────────────────────────────────────────────
    annulee_le = models.DateTimeField(
        null=True, blank=True, verbose_name="Annulée le"
    )
    annulee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='commandes_annulees',
        verbose_name="Annulée par",
    )
    motif_annulation = models.TextField(
        null=True, blank=True, verbose_name="Motif d'annulation"
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
        indexes = [
            models.Index(fields=['restaurant', 'statut']),
            models.Index(fields=['restaurant', 'date_commande']),
        ]

    def __str__(self):
        return (
            f"Commande #{self.id} — "
            f"{self.table.login} — "
            f"{self.get_statut_display()}"
        )

    def est_modifiable(self):
        return self.statut == 'en_attente'

    def peut_passer_en_livraison(self):
        # Une livraison part en course depuis l'état "prête à expédier" :
        #   - 'prete' si un plat passe par la cuisine ;
        #   - 'en_attente' si aucun plat ne nécessite la cuisine (étape sautée).
        if self.type_commande != 'livraison':
            return False
        if self.necessite_passage_cuisine():
            return self.statut == 'prete'
        return self.statut == 'en_attente'

    def est_livraison(self):
        return self.type_commande == 'livraison'

    def est_emporter(self):
        return self.type_commande == 'emporter'

    def est_sur_table(self):
        return self.type_commande == 'sur_table'

    def peut_etre_marquee_prete(self):
        return self.statut == 'en_attente'

    def peut_etre_servie(self):
        # Une livraison ne peut être marquée "Livrée" qu'après être partie en course
        # (statut 'en_livraison') — on ne saute jamais l'étape de livraison.
        if self.type_commande == 'livraison':
            return self.statut == 'en_livraison'
        # Sur place / à emporter : servie depuis 'prete', ou directement depuis
        # 'en_attente' quand aucun plat ne passe par la cuisine.
        return self.statut in ('prete', 'en_attente')

    def peut_etre_payee(self):
        return self.statut == 'servie'

    # ── Annulation ────────────────────────────────────────────────────────
    def peut_annuler_client(self):
        """Le client (propriétaire) annule tant que rien n'est engagé en cuisine."""
        return self.statut == 'en_attente'

    def peut_annuler_staff(self):
        """
        Le staff annule tant que la commande n'est ni servie/livrée, ni payée,
        ni déjà annulée (jusqu'à « en livraison » inclus).
        """
        return self.statut in ('en_attente', 'prete', 'en_livraison')

    def annuler(self, par, motif=""):
        """Passe la commande en ANNULÉE en traçant qui / quand / pourquoi."""
        self.statut = 'annulee'
        self.annulee_le = timezone.now()
        self.annulee_par = par
        self.motif_annulation = (motif or "").strip() or None
        self.save(update_fields=[
            'statut', 'annulee_le', 'annulee_par', 'motif_annulation', 'date_modification',
        ])

    def necessite_passage_cuisine(self):
        return self.items.filter(
            plat__necessite_validation_cuisine=True
        ).exists()


class CommandeItem(models.Model):
    """
    Ligne de commande : un plat dans une commande.
    Le prix_unitaire est capture au moment de la commande (snapshot).
    Isolation SaaS : heritee via commande → restaurant.
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
        verbose_name="Prix unitaire (snapshot)"
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


class LivraisonToken(models.Model):
    """
    Lien / QR public permettant à un livreur externe (sans compte) de suivre
    une commande de livraison précise et de la faire avancer
    (en course → livrée, et l'encaissement si le restaurant l'autorise).
    Le token est révocable : le régénérer invalide l'ancien lien.
    """
    commande = models.OneToOneField(
        Commande,
        on_delete=models.CASCADE,
        related_name='livraison_token',
        verbose_name="Commande",
    )
    token = models.CharField(max_length=64, unique=True, db_index=True, verbose_name="Token")
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='livraison_tokens_crees',
        verbose_name="Créé par",
        help_text="Membre du staff responsable du lien (attribution du paiement)",
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_derniere_utilisation = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Lien de livraison'
        verbose_name_plural = 'Liens de livraison'

    def __str__(self):
        return f"Lien livraison commande #{self.commande_id}"

    @classmethod
    def generer(cls, commande, cree_par=None):
        """Crée ou régénère le token d'une commande (invalide l'ancien lien)."""
        obj, _ = cls.objects.update_or_create(
            commande=commande,
            defaults={'token': secrets.token_urlsafe(48), 'cree_par': cree_par},
        )
        return obj

    def get_public_url(self):
        base = (getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
        return f"{base}/livraison/{self.token}"