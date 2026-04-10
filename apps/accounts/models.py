# apps/accounts/models.py
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.core.validators import EmailValidator, RegexValidator
from datetime import timedelta
import uuid


class UserManager(BaseUserManager):
    """
    Manager personnalisé pour le modèle User.
    USERNAME_FIELD = 'login' (requis par Django et utilisé pour les Rtable via QR)
    """

    def create_user(self, login, password=None, **extra_fields):
        if not login:
            raise ValueError("Le login est obligatoire")
        user = self.model(login=login, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, login, password=None, **extra_fields):
        """
        Crée un Super Admin Django (Rsuper_admin).
        Pas de restaurant associé — gère toute la plateforme.
        """
        extra_fields.setdefault('role', 'Rsuper_admin')
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('actif', True)
        extra_fields.setdefault('restaurant', None)

        if not extra_fields.get('nom_complet'):
            raise ValueError("Le nom complet est obligatoire pour un superutilisateur")
        if not extra_fields.get('email'):
            raise ValueError("L'email est obligatoire pour un superutilisateur")

        return self.create_user(login, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Modèle User personnalisé pour Restaurant Manager Pro v2.

    Connexion :
    - Rtable        : login + password (via QR Code ou formulaire)
    - Tous les autres : email + password

    USERNAME_FIELD = 'login' conservé pour :
    - Compatibilité Django (auth.E003)
    - Connexion QR Code des tables (login unique par table)
    """

    ROLE_CHOICES = [
        ('Rsuper_admin',    'Super Administrateur'),
        ('Radmin',          'Administrateur'),
        ('Rmanager',        'Manager'),
        ('Rserveur',        'Serveur'),
        ('Rchef_cuisinier', 'Chef Cuisinier'),
        ('Rcuisinier',      'Cuisinier'),
        ('Rcomptable',      'Comptable'),
        ('Rtable',          'Table'),
    ]

    login = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Login"
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        verbose_name="Rôle"
    )

    restaurant = models.ForeignKey(
        'company.Restaurant',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='users',
        verbose_name="Restaurant",
        help_text="Null uniquement pour le Super Admin"
    )

    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(default=timezone.now)

    must_change_password = models.BooleanField(
        default=False,
        verbose_name="Doit changer le mot de passe",
        help_text="Forcé à True à la création — reset à False après changement"
    )

    nom_complet = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name="Nom complet"
    )

    # Email unique sur toute la plateforme — utilisé pour la connexion (sauf Rtable)
    email = models.EmailField(
        max_length=254,
        blank=True,
        null=True,
        unique=True,
        validators=[EmailValidator()],
        verbose_name="Adresse email",
        help_text="Obligatoire pour tous les rôles sauf Rtable — unique sur toute la plateforme"
    )

    telephone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        validators=[
            RegexValidator(
                regex=r'^\+?[0-9]{9,20}$',
                message="Format valide: +224XXXXXXXXX ou XXXXXXXXX (9-20 chiffres)"
            )
        ],
        verbose_name="Numéro de téléphone"
    )

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    objects = UserManager()

    # Conservé pour Django + QR Login des tables
    USERNAME_FIELD = 'login'
    REQUIRED_FIELDS = ['nom_complet', 'email']

    class Meta:
        db_table = 'user'
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'

    def __str__(self):
        if self.nom_complet and not self.is_table():
            return f"{self.nom_complet} ({self.login})"
        return f"{self.login} ({self.get_role_display()})"

    # ── Helpers rôles ──────────────────────────────────────────────────────

    def is_super_admin(self):
        return self.role == 'Rsuper_admin'

    def is_admin(self):
        return self.role == 'Radmin'

    def is_manager(self):
        return self.role == 'Rmanager'

    def is_admin_or_manager(self):
        return self.role in ('Radmin', 'Rmanager')

    def is_serveur(self):
        return self.role == 'Rserveur'

    def is_chef_cuisinier(self):
        return self.role == 'Rchef_cuisinier'

    def is_cuisinier(self):
        return self.role == 'Rcuisinier'

    def is_cuisinier_any(self):
        return self.role in ('Rchef_cuisinier', 'Rcuisinier')

    def is_comptable(self):
        return self.role == 'Rcomptable'

    def is_table(self):
        return self.role == 'Rtable'

    def requires_personal_info(self):
        return self.role != 'Rtable'

    def get_restaurant_actif(self):
        if self.is_super_admin():
            return True
        return self.restaurant and self.restaurant.is_active


class PasswordResetToken(models.Model):
    """
    Token de réinitialisation de mot de passe demandé par l'utilisateur.
    Valable 1h — usage unique.
    Le frontend redirige vers /auth/reset-password?token=<uuid>
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='password_reset_tokens',
        verbose_name="Utilisateur"
    )

    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        verbose_name="Token"
    )

    expires_at = models.DateTimeField(verbose_name="Expiration")
    is_used = models.BooleanField(default=False, verbose_name="Utilisé")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Token de réinitialisation"
        verbose_name_plural = "Tokens de réinitialisation"
        ordering = ['-created_at']

    def __str__(self):
        statut = "UTILISÉ" if self.is_used else "ACTIF"
        return f"Reset {self.user.email} [{statut}]"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=1)
        super().save(*args, **kwargs)

    def est_valide(self):
        return not self.is_used and timezone.now() < self.expires_at

    def utiliser(self):
        self.is_used = True
        self.save(update_fields=['is_used'])

    @classmethod
    def creer_pour(cls, user):
        """Invalide les anciens tokens et crée un nouveau."""
        cls.objects.filter(user=user, is_used=False).update(is_used=True)
        return cls.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=1),
        )