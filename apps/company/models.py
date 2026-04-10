# apps/company/models.py
from django.db import models
from django.core.validators import EmailValidator, RegexValidator
from django.utils import timezone
from datetime import timedelta
import uuid


class Restaurant(models.Model):
    """
    Modele representant un tenant SaaS — un restaurant client.
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
    Valable 48h — usage unique.
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