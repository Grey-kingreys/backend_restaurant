# apps/company/models.py
from django.db import models
from django.core.validators import EmailValidator, RegexValidator
from django.utils import timezone
from datetime import timedelta
import uuid


class Restaurant(models.Model):
    """
    Modele representant un tenant SaaS - un restaurant client.
    Cree par le Super Admin uniquement.
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

    latitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        null=True, blank=True,
        verbose_name="Latitude GPS"
    )

    longitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        null=True, blank=True,
        verbose_name="Longitude GPS"
    )

    rayon_connexion = models.PositiveIntegerField(
        default=200,
        verbose_name="Rayon de connexion (m)",
        help_text="Distance maximale en metres pour se connecter via QR Code"
    )

    duree_session_table = models.PositiveIntegerField(
        default=60,
        verbose_name="Duree session table (min)",
        help_text="Duree maximale d'une session QR en minutes (30-120)"
    )

    accept_livraison = models.BooleanField(
        default=False,
        verbose_name="Accepte les commandes livraison",
        help_text="Active la commande en ligne avec livraison a domicile"
    )

    accept_emporter = models.BooleanField(
        default=False,
        verbose_name="Accepte les commandes a emporter",
        help_text="Active la commande en ligne avec retrait sur place"
    )

    # OBSOLETE - conserve pour ne pas perdre les montants deja saisis.
    # Les frais de livraison varient avec la distance : ils ne sont plus factures
    # dans la commande et se conviennent directement avec le livreur. Ce champ
    # n'est plus lu par l'application ni modifiable depuis l'interface.
    frais_livraison = models.DecimalField(
        max_digits=10, decimal_places=0,
        null=True, blank=True,
        verbose_name="Frais de livraison (GNF) - obsolete",
        help_text="Obsolete : les frais sont convenus avec le livreur selon la distance."
    )

    livraison_lien_autorise_paiement = models.BooleanField(
        default=False,
        verbose_name="Encaissement via lien de livraison",
        help_text="Autorise un livreur externe (lien / QR) à valider le paiement à la livraison"
    )

    # ── Réservations ──────────────────────────────────────────────────────
    reservation_validation_auto = models.BooleanField(
        default=True,
        verbose_name="Validation automatique des réservations",
        help_text="Si True, la réservation est confirmée immédiatement ; sinon le staff valide manuellement"
    )

    reservation_delai_annulation_heures = models.PositiveIntegerField(
        default=2,
        verbose_name="Délai d'annulation (heures)",
        help_text="Nombre d'heures avant l'heure de réservation jusqu'auquel le client peut annuler"
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
        self.is_active = False
        self.save(update_fields=['is_active', 'updated_at'])

    def reactiver(self):
        self.is_active = True
        self.save(update_fields=['is_active', 'updated_at'])

    def supprimer(self):
        """Supprime le restaurant et toutes ses donnees associees (cascade)."""
        self.delete()

    def get_slug(self):
        """
        Retourne un slug simple base sur le nom du restaurant.
        Utilise pour prefixer les logins (ex: lebaobab_admin).
        """
        import re
        slug = self.nom.lower()
        slug = slug.replace(' ', '')
        slug = re.sub(r'[^a-z0-9]', '', slug)
        return slug[:20]  # max 20 chars pour garder le login lisible


class OnboardingToken(models.Model):
    """
    Token de premier connexion pour l'Admin cree par le Super Admin.
    Valable 48h - usage unique.
    Apres utilisation : is_used=True, le token ne peut plus servir.
    Le frontend redirige vers /auth/first-login?token=<uuid>
    """

    user = models.OneToOneField(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='onboarding_token',
        verbose_name="Utilisateur"
    )

    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        verbose_name="Token"
    )

    expires_at = models.DateTimeField(
        verbose_name="Expiration"
    )

    is_used = models.BooleanField(
        default=False,
        verbose_name="Utilise"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Token d'onboarding"
        verbose_name_plural = "Tokens d'onboarding"

    def __str__(self):
        statut = "UTILISE" if self.is_used else "ACTIF"
        return f"Onboarding {self.user.login} [{statut}]"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=48)
        super().save(*args, **kwargs)

    def est_valide(self):
        return not self.is_used and timezone.now() < self.expires_at

    def utiliser(self):
        self.is_used = True
        self.save(update_fields=['is_used'])

    @classmethod
    def creer_pour(cls, user):
        """Cree ou renouvelle un token d'onboarding pour un utilisateur."""
        obj, _ = cls.objects.update_or_create(
            user=user,
            defaults={
                'token': uuid.uuid4(),
                'expires_at': timezone.now() + timedelta(hours=48),
                'is_used': False,
            }
        )
        return obj