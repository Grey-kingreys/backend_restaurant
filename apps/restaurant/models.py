# apps/restaurant/models.py
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from datetime import timedelta
import secrets
import uuid


class TableRestaurant(models.Model):
    """
    Table physique du restaurant.
    Liee a un utilisateur de type Rtable (OneToOne).
    Isolation SaaS : FK restaurant directe + heritee via utilisateur.
    """

    # ── Isolation SaaS ────────────────────────────────────────────────────
    restaurant = models.ForeignKey(
        'company.Restaurant',
        on_delete=models.CASCADE,
        related_name='tables',
        verbose_name="Restaurant"
    )

    # ── Champs metier ─────────────────────────────────────────────────────
    numero_table = models.CharField(
        max_length=10,
        verbose_name="Numero de table"
    )

    nombre_places = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Nombre de places"
    )

    utilisateur = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'Rtable'},
        related_name='table_restaurant',
        verbose_name="Utilisateur associe"
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Table"
        verbose_name_plural = "Tables"
        ordering = ['numero_table']
        # numero_table unique PAR restaurant
        unique_together = ['restaurant', 'numero_table']

    def __str__(self):
        return f"Table {self.numero_table} — {self.restaurant.nom} ({self.nombre_places} places)"

    def get_statut_actuel(self):
        """Retourne le statut actuel : libre | en_attente | prete | servie"""
        derniere = self.utilisateur.commandes.filter(
            statut__in=['en_attente', 'prete', 'servie']
        ).order_by('-date_commande').first()
        if not derniere:
            return 'libre'
        return derniere.statut

    def a_commande_active(self):
        """True si la table a une commande non payee"""
        return self.utilisateur.commandes.filter(
            statut__in=['en_attente', 'prete', 'servie']
        ).exists()


class TableToken(models.Model):
    """
    Token unique pour la connexion automatique via QR Code.
    Isolation SaaS : heritee via table (User → restaurant).
    Invalide si le mot de passe de la table change.
    """

    table = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'Rtable'},
        related_name='auth_token',
        verbose_name="Table associee"
    )

    token = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="Token d'authentification"
    )

    password_hash = models.CharField(
        max_length=128,
        verbose_name="Hash du mot de passe"
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_derniere_utilisation = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Token de table"
        verbose_name_plural = "Tokens de tables"

    def __str__(self):
        return f"Token — {self.table.login} ({self.table.restaurant.nom})"

    @classmethod
    def generer_token(cls, table):
        """Genere ou regenere un token securise pour une table."""
        nouveau_token = secrets.token_urlsafe(48)
        token_obj, _ = cls.objects.update_or_create(
            table=table,
            defaults={
                'token': nouveau_token,
                'password_hash': table.password,
            }
        )
        return token_obj

    def est_valide(self):
        """Invalide si le mot de passe de la table a change."""
        return self.password_hash == self.table.password

    def marquer_utilise(self):
        self.date_derniere_utilisation = timezone.now()
        self.save(update_fields=['date_derniere_utilisation'])


class TableSession(models.Model):
    """
    Session de connexion pour une table — creee a chaque scan de QR Code.
    Isolation SaaS : heritee via table (User → restaurant).
    Expire 1 minute apres le paiement de toutes les commandes de la session.
    """

    table = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'Rtable'},
        related_name='sessions',
        verbose_name="Table"
    )

    session_token = models.CharField(
        max_length=64,
        unique=True,
        default=uuid.uuid4,
        verbose_name="Token de session"
    )

    django_session_key = models.CharField(
        max_length=40,
        unique=True,
        verbose_name="Cle de session Django"
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_derniere_activite = models.DateTimeField(auto_now=True)

    commande_payee = models.ForeignKey(
        'commandes.Commande',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='session_associee',
        verbose_name="Commande payee"
    )

    date_paiement = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date du paiement"
    )

    est_active = models.BooleanField(
        default=True,
        verbose_name="Session active"
    )

    class Meta:
        verbose_name = "Session de table"
        verbose_name_plural = "Sessions de tables"
        ordering = ['-date_creation']

    def __str__(self):
        return f"Session {self.table.login} — {self.date_creation}"

    def marquer_payement(self, commande):
        self.commande_payee = commande
        self.date_paiement = timezone.now()
        self.save(update_fields=['commande_payee', 'date_paiement'])

    def doit_etre_expiree(self):
        if not self.date_paiement:
            return False
        return (timezone.now() - self.date_paiement) > timedelta(minutes=1)

    def expirer(self):
        self.est_active = False
        self.save(update_fields=['est_active'])

    @classmethod
    def nettoyer_sessions_expirees(cls):
        sessions = cls.objects.filter(
            est_active=True,
            date_paiement__isnull=False,
            date_paiement__lt=timezone.now() - timedelta(minutes=1)
        )
        return sessions.update(est_active=False)