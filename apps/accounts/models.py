# apps/accounts/models.py
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.core.validators import EmailValidator, RegexValidator


class UserManager(BaseUserManager):
    """
    Manager personnalise pour le modele User.
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
        """
        Cree un Super Admin Django (Rsuper_admin).
        Pas de restaurant associe — gere toute la plateforme.
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
    Modele User personnalise pour Restaurant Manager Pro v2.

    Roles disponibles :
    - Rsuper_admin    : Gere la plateforme SaaS — cree les restaurants [NOUVEAU v2]
    - Radmin          : Acces total au restaurant — cree par le Super Admin
    - Rmanager        : Comme Admin mais sans suppression [NOUVEAU v2]
    - Rserveur        : Sert les tables, valide paiements
    - Rchef_cuisinier : Gere le menu (CRUD plats)
    - Rcuisinier      : Prepare les commandes en cuisine
    - Rcomptable      : Gere la caisse et les depenses
    - Rtable          : Client a la table (commande via tablette)

    Isolation SaaS :
    - Tous les roles sauf Rsuper_admin ont une FK restaurant obligatoire
    - login est unique globalement (contrainte Django obligatoire sur USERNAME_FIELD)
    - Le serializer de creation prefixe le login avec le slug du restaurant
      pour eviter les collisions entre restaurants (ex: "lebaobab_admin")
    - Le Super Admin n'appartient a aucun restaurant (restaurant=None)
    """

    ROLE_CHOICES = [
        ('Rsuper_admin',    'Super Administrateur'),   # NOUVEAU v2 — gere la plateforme
        ('Radmin',          'Administrateur'),
        ('Rmanager',        'Manager'),                # NOUVEAU v2 — comme admin sans delete
        ('Rserveur',        'Serveur'),
        ('Rchef_cuisinier', 'Chef Cuisinier'),
        ('Rcuisinier',      'Cuisinier'),
        ('Rcomptable',      'Comptable'),
        ('Rtable',          'Table'),
    ]

    # unique=True obligatoire : Django exige que USERNAME_FIELD soit unique (auth.E003)
    # Le serializer de creation gerera les collisions via prefixe slug restaurant
    login = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Login"
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        verbose_name="Role"
    )

    # FK vers le restaurant — NULL uniquement pour Rsuper_admin
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

    # Force le changement de mot de passe a la premiere connexion
    # Mis a True automatiquement lors de la creation par l'Admin
    must_change_password = models.BooleanField(
        default=False,
        verbose_name="Doit changer le mot de passe",
        help_text="Force a True a la creation par l'Admin — reset a False apres changement"
    )

    # Informations personnelles — obligatoires pour tous les roles sauf Rtable
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

    # ── Methodes helper roles ──────────────────────────────────────────────

    def is_super_admin(self):
        return self.role == 'Rsuper_admin'

    def is_admin(self):
        return self.role == 'Radmin'

    def is_manager(self):
        return self.role == 'Rmanager'

    def is_admin_or_manager(self):
        """True si Radmin OU Rmanager"""
        return self.role in ('Radmin', 'Rmanager')

    def is_serveur(self):
        return self.role == 'Rserveur'

    def is_chef_cuisinier(self):
        return self.role == 'Rchef_cuisinier'

    def is_cuisinier(self):
        return self.role == 'Rcuisinier'

    def is_cuisinier_any(self):
        """True si Chef Cuisinier OU Cuisinier executant"""
        return self.role in ('Rchef_cuisinier', 'Rcuisinier')

    def is_comptable(self):
        return self.role == 'Rcomptable'

    def is_table(self):
        return self.role == 'Rtable'

    def requires_personal_info(self):
        """True si le role necessite nom_complet + email + telephone"""
        return self.role != 'Rtable'

    def get_restaurant_actif(self):
        """
        Retourne True si le restaurant du user est actif.
        Toujours True pour le Super Admin (pas de restaurant).
        """
        if self.is_super_admin():
            return True
        return self.restaurant and self.restaurant.is_active