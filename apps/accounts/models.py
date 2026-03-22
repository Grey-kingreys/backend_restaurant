# apps/accounts/models.py
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.core.validators import EmailValidator, RegexValidator


class UserManager(BaseUserManager):
    """
    Manager personnalise pour le modele User
    USERNAME_FIELD = 'login' (pas 'username')
    """

    def create_user(self, login, password=None, **extra_fields):
        if not login:
            raise ValueError("Le login est obligatoire")
        user = self.model(login=login, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, login, password=None, **extra_fields):
        extra_fields.setdefault('role', 'Radmin')
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('actif', True)

        if not extra_fields.get('nom_complet'):
            raise ValueError("Le nom complet est obligatoire pour un superutilisateur")
        if not extra_fields.get('email'):
            raise ValueError("L'email est obligatoire pour un superutilisateur")
        if not extra_fields.get('telephone'):
            raise ValueError("Le telephone est obligatoire pour un superutilisateur")

        return self.create_user(login, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Modele User personnalise pour le systeme de restaurant.

    Roles disponibles (v2.0) :
    - Rtable          : Client a la table (commande via tablette)
    - Rserveur        : Sert les tables, valide paiements
    - Rchef_cuisinier : Gere le menu (CRUD plats) - NOUVEAU v2.0
    - Rcuisinier      : Prepare les commandes en cuisine - NOUVEAU v2.0
    - Rcomptable      : Gere la caisse et les depenses
    - Radmin          : Acces total
    """

    ROLE_CHOICES = [
        ('Rtable',          'Table'),
        ('Rserveur',        'Serveur'),
        ('Rchef_cuisinier', 'Chef Cuisinier'),   # NOUVEAU v2.0
        ('Rcuisinier',      'Cuisinier'),         # NOUVEAU v2.0 (executant cuisine)
        ('Rcomptable',      'Comptable'),
        ('Radmin',          'Administrateur'),
    ]

    # Champs principaux
    login = models.CharField(max_length=50, unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(default=timezone.now)

    # Informations personnelles
    # Obligatoires pour tous les roles sauf Rtable
    nom_complet = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name="Nom complet",
        help_text="Obligatoire pour tous les roles sauf Rtable"
    )

    email = models.EmailField(
        max_length=254,
        blank=True,
        null=True,
        validators=[EmailValidator()],
        verbose_name="Adresse email",
        help_text="Obligatoire pour tous les roles sauf Rtable"
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
        verbose_name="Numero de telephone",
        help_text="Obligatoire pour tous les roles sauf Rtable"
    )

    # Champs requis par Django
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    objects = UserManager()

    # Login comme identifiant au lieu de username
    USERNAME_FIELD = 'login'
    REQUIRED_FIELDS = ['nom_complet', 'email', 'telephone']

    class Meta:
        db_table = 'user'
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'

    def __str__(self):
        if self.nom_complet and not self.is_table():
            return f"{self.nom_complet} ({self.login})"
        return f"{self.login} ({self.get_role_display()})"

    # Methodes helper pour verifier les roles
    def is_table(self):
        return self.role == 'Rtable'

    def is_serveur(self):
        return self.role == 'Rserveur'

    def is_chef_cuisinier(self):
        return self.role == 'Rchef_cuisinier'

    def is_cuisinier(self):
        return self.role == 'Rcuisinier'

    def is_cuisinier_any(self):
        """True si chef cuisinier OU cuisinier executant"""
        return self.role in ('Rchef_cuisinier', 'Rcuisinier')

    def is_comptable(self):
        return self.role == 'Rcomptable'

    def is_admin(self):
        return self.role == 'Radmin'

    def requires_personal_info(self):
        """Retourne True si le role necessite des infos personnelles"""
        return self.role != 'Rtable'