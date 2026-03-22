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
    """

    numero_table = models.CharField(
        max_length=10,
        unique=True,
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

    def __str__(self):
        return f"Table {self.numero_table} ({self.nombre_places} places)"

    def get_statut_actuel(self):
        """
        Retourne le statut actuel de la table.
        LIBRE | en_attente | prete | servie
        """
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
    Invalide automatiquement si le mot de passe de la table change
    (password_hash ne correspond plus).
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

    # Hash du mot de passe au moment de la generation
    # Permet de detecter si le mot de passe a change
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
        return f"Token - {self.table.login}"

    @classmethod
    def generer_token(cls, table):
        """
        Genere ou regenere un token securise pour une table.
        Retourne l'instance TableToken.
        """
        nouveau_token = secrets.token_urlsafe(48)
        token_obj, created = cls.objects.update_or_create(
            table=table,
            defaults={
                'token': nouveau_token,
                'password_hash': table.password,
            }
        )
        return token_obj

    def est_valide(self):
        """
        Verifie si le token est encore valide.
        Invalide si le mot de passe de la table a change.
        """
        return self.password_hash == self.table.password

    def marquer_utilise(self):
        """Enregistre la date d'utilisation du token"""
        self.date_derniere_utilisation = timezone.now()
        self.save(update_fields=['date_derniere_utilisation'])

    def get_qr_url(self, request):
        """Retourne l'URL complete pour le QR Code"""
        from django.urls import reverse
        path = reverse('restaurant:qr_login', kwargs={'token': self.token})
        return request.build_absolute_uri(path)


class TableSession(models.Model):
    """
    Session de connexion pour une table.
    Creee a chaque scan de QR Code.
    Expire automatiquement 1 minute apres le paiement de la commande.

    Utilisee par AutoLogoutTableMiddleware pour deconnecter
    automatiquement la table apres paiement.
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

    # Marqueur de paiement - lance le compte a rebours de 1 minute
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
        return f"Session {self.table.login} - {self.date_creation}"

    def marquer_payement(self, commande):
        """
        Marque qu'une commande a ete payee.
        Lance le compte a rebours d'expiration de 1 minute.
        """
        self.commande_payee = commande
        self.date_paiement = timezone.now()
        self.save(update_fields=['commande_payee', 'date_paiement'])

    def doit_etre_expiree(self):
        """
        Retourne True si 1 minute s'est ecoulee depuis le paiement.
        """
        if not self.date_paiement:
            return False
        temps_ecoule = timezone.now() - self.date_paiement
        return temps_ecoule > timedelta(minutes=1)

    def expirer(self):
        """Marque la session comme inactive"""
        self.est_active = False
        self.save(update_fields=['est_active'])

    @classmethod
    def nettoyer_sessions_expirees(cls):
        """
        Nettoie les sessions expirees.
        Appele par le middleware a chaque requete.
        """
        sessions_a_expirer = cls.objects.filter(
            est_active=True,
            date_paiement__isnull=False,
            date_paiement__lt=timezone.now() - timedelta(minutes=1)
        )
        count = sessions_a_expirer.update(est_active=False)
        return count