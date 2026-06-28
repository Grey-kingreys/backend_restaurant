# apps/restaurant/models.py
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from datetime import timedelta
import secrets
import uuid
import math


def haversine(lat1, lon1, lat2, lon2):
    """Distance en metres entre deux coordonnees GPS (formule haversine)."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


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
    def get_qr_url(self, request):
        """Construit l'URL frontend de connexion automatique encodee dans le QR Code."""
        from django.conf import settings
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        return f"{frontend_url}/auth/qr/{self.token}/"


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

    expires_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Expiration de session"
    )

    lat_connexion = models.DecimalField(
        max_digits=9, decimal_places=6,
        null=True, blank=True,
        verbose_name="Latitude de connexion"
    )

    lng_connexion = models.DecimalField(
        max_digits=9, decimal_places=6,
        null=True, blank=True,
        verbose_name="Longitude de connexion"
    )

    nb_echecs_gps = models.PositiveIntegerField(
        default=0,
        verbose_name="Nombre d'echecs GPS consecutifs"
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

    def est_hors_zone(self, lat, lng):
        """Retourne True si la position est hors du rayon du restaurant."""
        resto = self.table.restaurant
        if not (resto.latitude and resto.longitude):
            return False
        dist = haversine(float(lat), float(lng), float(resto.latitude), float(resto.longitude))
        return dist > resto.rayon_connexion

    def incrementer_echec_gps(self):
        self.nb_echecs_gps += 1
        self.save(update_fields=['nb_echecs_gps'])
        return self.nb_echecs_gps

    def reinitialiser_echecs_gps(self):
        if self.nb_echecs_gps > 0:
            self.nb_echecs_gps = 0
            self.save(update_fields=['nb_echecs_gps'])

    @classmethod
    def nettoyer_sessions_expirees(cls):
        sessions = cls.objects.filter(
            est_active=True,
            date_paiement__isnull=False,
            date_paiement__lt=timezone.now() - timedelta(minutes=1)
        )
        return sessions.update(est_active=False)

# ─────────────────────────────────────────────────────────────────────────────
# RÉSERVATION DE TABLE (Client externe Rclient)
# ─────────────────────────────────────────────────────────────────────────────

# Durée pendant laquelle une table est considérée occupée par une réservation.
# Durée d'occupation d'une table selon la taille du groupe (minutes).
# Plus le groupe est grand, plus le repas est long.
RESERVATION_BUFFER_MINUTES = 15  # nettoyage / remise en place entre deux réservations


def duree_reservation_minutes(nombre_personnes):
    """Durée d'occupation (minutes) attribuée à une réservation selon le nombre de couverts."""
    n = max(1, int(nombre_personnes or 1))
    if n <= 2:
        return 90
    if n <= 4:
        return 120
    return 150


# Conservé pour rétro-compatibilité (anciens appels) — durée par défaut moyenne.
RESERVATION_DUREE = timedelta(minutes=120)


class Reservation(models.Model):
    """
    Réservation d'une table physique par un client externe (Rclient).
    Workflow : en_attente → (confirmee | refusee) ; le client peut annuler.
    Conflit : une table déjà réservée (en_attente/confirmee) sur un créneau de
    ±2h le même jour n'est plus disponible.
    """

    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('confirmee',  'Confirmée'),
        ('refusee',    'Refusée'),
        ('annulee',    'Annulée'),
        ('terminee',   'Terminée'),
        ('no_show',    'Absent (no-show)'),
    ]
    # Statuts qui « occupent » la table pour le calcul des conflits
    STATUTS_ACTIFS = ('en_attente', 'confirmee')
    # Statuts qui pénalisent la fiabilité du client (no-show)
    STATUTS_NO_SHOW = ('no_show',)
    # Seuil de no-shows à partir duquel le staff reçoit un avertissement
    SEUIL_AVERTISSEMENT_NO_SHOW = 3

    restaurant = models.ForeignKey(
        'company.Restaurant', on_delete=models.CASCADE,
        related_name='reservations', verbose_name="Restaurant"
    )
    table = models.ForeignKey(
        TableRestaurant, on_delete=models.CASCADE,
        related_name='reservations', verbose_name="Table"
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='reservations', verbose_name="Client",
        limit_choices_to={'role': 'Rclient'}
    )
    date_reservation = models.DateField(verbose_name="Date de la réservation")
    heure = models.TimeField(verbose_name="Heure")
    nombre_personnes = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1)], verbose_name="Nombre de personnes"
    )
    duree_minutes = models.PositiveIntegerField(
        default=120, verbose_name="Durée d'occupation (min)",
        help_text="Durée attribuée selon le nombre de couverts (figée à la création)"
    )
    note = models.TextField(blank=True, default="", verbose_name="Note / demande spéciale")
    statut = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default='en_attente', verbose_name="Statut"
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Réservation"
        verbose_name_plural = "Réservations"
        ordering = ['-date_reservation', '-heure']
        indexes = [
            models.Index(fields=['restaurant', 'statut']),
            models.Index(fields=['table', 'date_reservation']),
        ]

    def __str__(self):
        t = self.table.numero_table if self.table_id else '—'
        return f"Réservation T{t} — {self.date_reservation} {self.heure} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        # Fige la durée d'occupation selon la taille du groupe si non définie.
        if not self.duree_minutes:
            self.duree_minutes = duree_reservation_minutes(self.nombre_personnes)
        super().save(*args, **kwargs)

    @staticmethod
    def _plage(heure, duree_minutes):
        """Renvoie (debut, fin) en datetimes — fin inclut le buffer de nettoyage."""
        from datetime import datetime, date as _date
        debut = datetime.combine(_date.min, heure)
        fin = debut + timedelta(minutes=int(duree_minutes) + RESERVATION_BUFFER_MINUTES)
        return debut, fin

    @staticmethod
    def table_est_disponible(table, date_reservation, heure, nombre_personnes=None,
                             duree_minutes=None, exclure_id=None):
        """
        Vrai si la table n'a aucune réservation active dont la plage
        [début, fin+buffer] chevauche celle demandée, le même jour.
        La durée est dérivée du nombre de personnes si non fournie.
        """
        if duree_minutes is None:
            duree_minutes = duree_reservation_minutes(nombre_personnes or 1)
        deb_a, fin_a = Reservation._plage(heure, duree_minutes)

        qs = Reservation.objects.filter(
            table=table,
            date_reservation=date_reservation,
            statut__in=Reservation.STATUTS_ACTIFS,
        )
        if exclure_id:
            qs = qs.exclude(pk=exclure_id)
        for r in qs:
            deb_b, fin_b = Reservation._plage(r.heure, r.duree_minutes or 120)
            # Chevauchement strict de deux intervalles
            if deb_a < fin_b and deb_b < fin_a:
                return False
        return True

    @staticmethod
    def no_show_count(client):
        """Nombre total de no-shows enregistrés pour ce client (tous restaurants)."""
        return Reservation.objects.filter(
            client=client, statut__in=Reservation.STATUTS_NO_SHOW
        ).count()

    @staticmethod
    def trouver_table_disponible(restaurant, date_reservation, heure, nombre_personnes,
                                 exclure_id=None):
        """
        Attribution automatique : renvoie la plus petite table dont la capacité
        suffit et qui est libre sur le créneau, ou None si tout est complet.
        """
        duree = duree_reservation_minutes(nombre_personnes)
        candidates = (
            TableRestaurant.objects
            .filter(restaurant=restaurant, nombre_places__gte=nombre_personnes)
            .order_by('nombre_places', 'numero_table')
        )
        for t in candidates:
            if Reservation.table_est_disponible(
                t, date_reservation, heure,
                duree_minutes=duree, exclure_id=exclure_id,
            ):
                return t
        return None


class ReservationClientBloque(models.Model):
    """
    Blocage manuel d'un client par un restaurant (après des no-shows répétés).
    Un client bloqué ne peut plus réserver dans ce restaurant.
    """
    restaurant = models.ForeignKey(
        'company.Restaurant', on_delete=models.CASCADE,
        related_name='clients_bloques', verbose_name="Restaurant"
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='blocages_reservation', verbose_name="Client",
        limit_choices_to={'role': 'Rclient'}
    )
    raison = models.CharField(max_length=255, blank=True, default="", verbose_name="Raison")
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Client bloqué (réservation)"
        verbose_name_plural = "Clients bloqués (réservation)"
        unique_together = ['restaurant', 'client']

    def __str__(self):
        return f"{self.client} bloqué chez {self.restaurant.nom}"
