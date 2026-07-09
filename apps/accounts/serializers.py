# apps/accounts/serializers.py
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.db import transaction
import logging

from .models import User, PasswordResetToken, Permission, RoleConfig
from .services.email_service import send_password_reset_email

logger = logging.getLogger(__name__)


def get_role_config_for_role(role: str) -> RoleConfig | None:
    """
    Récupère le RoleConfig système pour un rôle donné.
    Utilisé lors de la création d'utilisateurs pour assigner automatiquement
    les permissions appropriées au rôle.
    """
    try:
        return RoleConfig.objects.get(slug=role, is_system=True)
    except RoleConfig.DoesNotExist:
        logger.warning(
            f"RoleConfig système introuvable pour le rôle '{role}' — "
            f"l'utilisateur n'aura pas de permissions"
        )
        return None


# ─────────────────────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────────────────────

class LoginSerializer(serializers.Serializer):
    """
    Serializer de connexion unifié.

    - Rtable          : login + password  (QR Code ou formulaire)
    - Tous les autres : email + password

    Retourne access + refresh + payload enrichi (role, nom_complet, restaurant_id).
    """
    email = serializers.EmailField(required=False)
    login = serializers.CharField(required=False)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email')
        login = data.get('login')
        password = data.get('password')

        if not email and not login:
            raise serializers.ValidationError(
                "Fournissez un email (staff) ou un login (table)."
            )

        user = None

        if email:
            # Connexion par email — tous les rôles sauf Rtable
            try:
                user_obj = User.objects.get(email=email)
                # Rtable n'a pas d'email — sécurité supplémentaire
                if user_obj.is_table():
                    raise serializers.ValidationError(
                        "Les comptes table se connectent via login, pas email."
                    )
                user = authenticate(
                    request=self.context.get('request'),
                    username=user_obj.login,
                    password=password
                )
            except User.DoesNotExist:
                pass

        elif login:
            # Connexion par login — Rtable uniquement
            try:
                user_obj = User.objects.get(login=login)
                if not user_obj.is_table():
                    raise serializers.ValidationError(
                        "Utilisez votre email pour vous connecter."
                    )
                user = authenticate(
                    request=self.context.get('request'),
                    username=login,
                    password=password
                )
            except User.DoesNotExist:
                pass

        if not user:
            raise serializers.ValidationError("Identifiants invalides.")

        if not user.is_active:
            raise serializers.ValidationError(
                "Compte inactif. Utilisez le lien de première connexion reçu par email."
            )

        if not user.actif:
            raise serializers.ValidationError(
                "Votre compte a été désactivé. Contactez votre administrateur."
            )

        # Vérification restaurant actif (sauf Super Admin et Client — non liés à un restaurant)
        if not user.is_super_admin() and not user.is_client():
            if not user.restaurant or not user.restaurant.is_active:
                raise serializers.ValidationError(
                    "Votre restaurant est suspendu. Contactez le support."
                )

        data['user'] = user
        return data

    def get_tokens(self, user):
        refresh = RefreshToken.for_user(user)
        # Enrichir le payload JWT
        refresh['role'] = user.role
        refresh['nom_complet'] = user.nom_complet
        refresh['restaurant_id'] = user.restaurant_id
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }


class LogoutSerializer(serializers.Serializer):
    """Blackliste le refresh token à la déconnexion."""
    refresh = serializers.CharField()

    def validate_refresh(self, value):
        try:
            token = RefreshToken(value)
            token.verify()
        except Exception:
            raise serializers.ValidationError("Token invalide ou déjà expiré.")
        self.token = token
        return value

    def save(self):
        self.token.blacklist()


# ─────────────────────────────────────────────────────────────────────────────
# PROFIL UTILISATEUR
# ─────────────────────────────────────────────────────────────────────────────

class UserMeSerializer(serializers.ModelSerializer):
    """Profil de l'utilisateur connecté — lecture seule."""
    restaurant_nom = serializers.SerializerMethodField()
    statut         = serializers.SerializerMethodField()
    permissions    = serializers.SerializerMethodField()
    role_config_id = serializers.SerializerMethodField()
    dashboard_type = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'login', 'role', 'nom_complet', 'email', 'telephone',
            'restaurant', 'restaurant_nom', 'actif', 'statut',
            'must_change_password', 'date_creation',
            'permissions', 'role_config_id', 'dashboard_type',
        ]
        read_only_fields = fields

    def get_restaurant_nom(self, obj):
        return obj.restaurant.nom if obj.restaurant else None

    def get_statut(self, obj):
        return "actif" if obj.actif else "inactif"

    def get_permissions(self, obj):
        """Liste des codes de permissions de l'utilisateur."""
        return sorted(obj.get_all_permissions_codes())

    def get_role_config_id(self, obj):
        return obj.role_config_id

    def get_dashboard_type(self, obj):
        if obj.role_config_id:
            return obj.role_config.dashboard_type
        if obj.is_super_admin():
            return 'superadmin'
        if obj.is_table():
            return 'table'
        return None


class UpdateMeSerializer(serializers.ModelSerializer):
    """Auto-édition du profil par l'utilisateur connecté (tous rôles réels)."""

    class Meta:
        model = User
        fields = ['nom_complet', 'email', 'telephone']

    def validate_nom_complet(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Le nom complet est requis.")
        return value

    def validate_email(self, value):
        value = (value or "").strip() or None
        if value:
            qs = User.objects.filter(email=value).exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError("Un utilisateur avec cet email existe déjà.")
        elif not self.instance.is_table():
            # email obligatoire pour les comptes humains (les Rtable n'en ont pas)
            raise serializers.ValidationError("L'email est requis.")
        return value


# ─────────────────────────────────────────────────────────────────────────────
# CRUD UTILISATEURS
# ─────────────────────────────────────────────────────────────────────────────

class UserListSerializer(serializers.ModelSerializer):
    """Serializer liste — données réduites pour la pagination."""
    restaurant_nom = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'login', 'role', 'nom_complet', 'email',
            'telephone', 'restaurant', 'restaurant_nom',
            'actif', 'must_change_password', 'date_creation',
        ]

    def get_restaurant_nom(self, obj):
        return obj.restaurant.nom if obj.restaurant else None


class UserDetailSerializer(serializers.ModelSerializer):
    """Serializer détail — toutes les infos."""
    restaurant_nom = serializers.SerializerMethodField()
    role_display = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'login', 'role', 'role_display', 'nom_complet',
            'email', 'telephone', 'restaurant', 'restaurant_nom',
            'actif', 'must_change_password', 'is_staff',
            'date_creation', 'last_login',
        ]
        read_only_fields = ['id', 'login', 'date_creation', 'last_login']

    def get_restaurant_nom(self, obj):
        return obj.restaurant.nom if obj.restaurant else None

    def get_role_display(self, obj):
        return obj.get_role_display()


class UserCreateSerializer(serializers.ModelSerializer):
    """
    Création d'un utilisateur par l'Admin ou le Manager.

    Règles :
    - Le login est généré automatiquement : {slug_restaurant}_{role_court}_{id}
    - Seul l'Admin peut créer un Radmin ou Rmanager
    - Le restaurant est automatiquement celui du créateur
    - must_change_password = True par défaut
    - Email requis pour tous sauf Rtable
    """
    password = serializers.CharField(
        write_only=True, min_length=8, required=True, allow_blank=False,
        error_messages={
            'required': "Le mot de passe est obligatoire.",
            'blank': "Le mot de passe est obligatoire.",
            'min_length': "Le mot de passe doit contenir au moins 8 caractères.",
        },
    )

    class Meta:
        model = User
        fields = [
            'role', 'nom_complet', 'email', 'telephone', 'password',
        ]

    ROLE_LOGIN_MAP = {
        'Radmin':          'admin',
        'Rmanager':        'manager',
        'Rserveur':        'serveur',
        'Rchef_cuisinier': 'chef',
        'Rcuisinier':      'cuisinier',
        'Rcomptable':      'comptable',
        'Rtable':          'table',
    }

    def validate_role(self, value):
        request = self.context['request']
        creator = request.user

        if value == 'Rsuper_admin':
            raise serializers.ValidationError(
                "Impossible de créer un Super Admin via cette route."
            )
        # Seul l'Admin peut créer Admin/Manager
        if value in ('Radmin', 'Rmanager') and not creator.is_admin():
            raise serializers.ValidationError(
                "Seul l'Administrateur peut créer un Admin ou Manager."
            )
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "Un utilisateur avec cet email existe déjà."
            )
        return value

    def validate(self, data):
        role = data.get('role')
        email = data.get('email')

        # Email obligatoire pour tous sauf Rtable
        if role != 'Rtable' and not email:
            raise serializers.ValidationError({
                'email': "L'email est obligatoire pour ce rôle."
            })
        # nom_complet obligatoire pour tous sauf Rtable
        if role != 'Rtable' and not data.get('nom_complet'):
            raise serializers.ValidationError({
                'nom_complet': "Le nom complet est obligatoire pour ce rôle."
            })
        return data

    def _generate_login(self, restaurant, role):
        """Génère un login unique : {slug}_{role_court}_{n}"""
        slug = restaurant.get_slug()
        role_court = self.ROLE_LOGIN_MAP.get(role, 'user')
        base = f"{slug}_{role_court}"
        login = base
        counter = 1
        while User.objects.filter(login=login).exists():
            login = f"{base}{counter}"
            counter += 1
        return login

    @transaction.atomic
    def create(self, validated_data):
        request = self.context['request']
        restaurant = request.user.restaurant
        role = validated_data['role']
        password = validated_data.pop('password', None)

        login = self._generate_login(restaurant, role)

        # Assigner automatiquement le RoleConfig en fonction du rôle
        role_config = get_role_config_for_role(role)

        user = User.objects.create_user(
            login=login,
            password=password,
            role=role,
            restaurant=restaurant,
            nom_complet=validated_data.get('nom_complet'),
            email=validated_data.get('email'),
            telephone=validated_data.get('telephone'),
            must_change_password=True,
            actif=True,
            role_config=role_config,  # Assigner les permissions du rôle
        )
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """Mise à jour partielle — Admin/Manager."""

    class Meta:
        model = User
        fields = ['nom_complet', 'email', 'telephone', 'role']

    def validate_email(self, value):
        if value:
            qs = User.objects.filter(email=value).exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "Un utilisateur avec cet email existe déjà."
                )
        return value

    def validate_role(self, value):
        request = self.context['request']
        if value == 'Rsuper_admin':
            raise serializers.ValidationError("Rôle non autorisé.")
        if value in ('Radmin', 'Rmanager') and not request.user.is_admin():
            raise serializers.ValidationError(
                "Seul l'Administrateur peut attribuer ce rôle."
            )
        return value


# ─────────────────────────────────────────────────────────────────────────────
# RESET MOT DE PASSE
# ─────────────────────────────────────────────────────────────────────────────

class AdminPasswordResetSerializer(serializers.Serializer):
    """
    Reset du mot de passe d'un utilisateur par l'Admin.
    Génère un nouveau mot de passe temporaire et force must_change_password=True.
    """
    new_password = serializers.CharField(min_length=8, write_only=True)

    def save(self, user):
        user.set_password(self.validated_data['new_password'])
        user.must_change_password = True
        user.save(update_fields=['password', 'must_change_password'])
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Demande de réinitialisation par l'utilisateur via son email.
    On ne confirme pas si l'email existe (sécurité anti-énumération).
    """
    email = serializers.EmailField()

    def validate_email(self, value):
        # On stocke l'utilisateur si trouvé, sinon on continue silencieusement
        try:
            user = User.objects.get(email=value, is_active=True, actif=True)
            if user.is_table():
                raise serializers.ValidationError(
                    "Les comptes table ne peuvent pas réinitialiser leur mot de passe par email."
                )
            self._user = user
        except User.DoesNotExist:
            self._user = None
        return value

    def save(self):
        user = getattr(self, '_user', None)
        if user:
            token = PasswordResetToken.creer_pour(user)
            send_password_reset_email(user, token)
        # Retourne toujours True — pas de fuite d'info
        return True


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Confirmation de réinitialisation via le token reçu par email.
    """
    token = serializers.UUIDField()
    password = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({
                'password_confirm': "Les mots de passe ne correspondent pas."
            })
        try:
            reset_token = PasswordResetToken.objects.select_related('user').get(
                token=data['token']
            )
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError({'token': "Token invalide."})

        if not reset_token.est_valide():
            raise serializers.ValidationError({
                'token': "Ce lien a expiré ou a déjà été utilisé."
            })

        data['reset_token'] = reset_token
        return data

    @transaction.atomic
    def save(self):
        reset_token = self.validated_data['reset_token']
        user = reset_token.user
        user.set_password(self.validated_data['password'])
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password'])
        reset_token.utiliser()
        return user


class ChangePasswordSerializer(serializers.Serializer):
    """
    Changement de mot de passe par l'utilisateur connecté.
    Utilisé aussi pour le first-login (must_change_password=True).
    """
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(min_length=8, write_only=True)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value

    def validate(self, data):
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError({
                'new_password_confirm': "Les mots de passe ne correspondent pas."
            })
        return data

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password'])
        return user


# ─────────────────────────────────────────────────────────────────────────────
# ROLES & PERMISSIONS
# ─────────────────────────────────────────────────────────────────────────────

class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ['id', 'code', 'label', 'categorie']


class RoleConfigListSerializer(serializers.ModelSerializer):
    permissions_count = serializers.SerializerMethodField()
    users_count       = serializers.SerializerMethodField()
    dashboard_label   = serializers.SerializerMethodField()

    class Meta:
        model = RoleConfig
        fields = [
            'id', 'nom', 'slug', 'is_system', 'dashboard_type', 'dashboard_label',
            'permissions_count', 'users_count',
        ]

    def get_permissions_count(self, obj):
        return obj.permissions.count()

    def get_users_count(self, obj):
        return obj.users.count()

    def get_dashboard_label(self, obj):
        return dict(RoleConfig.DASHBOARD_CHOICES).get(obj.dashboard_type, obj.dashboard_type)


class RoleConfigDetailSerializer(serializers.ModelSerializer):
    permissions     = PermissionSerializer(many=True, read_only=True)
    permission_codes = serializers.SerializerMethodField()
    users_count     = serializers.SerializerMethodField()
    dashboard_label = serializers.SerializerMethodField()

    class Meta:
        model = RoleConfig
        fields = [
            'id', 'nom', 'slug', 'is_system', 'dashboard_type', 'dashboard_label',
            'permissions', 'permission_codes', 'users_count',
        ]

    def get_permission_codes(self, obj):
        return sorted(obj.get_permission_codes())

    def get_users_count(self, obj):
        return obj.users.count()

    def get_dashboard_label(self, obj):
        return dict(RoleConfig.DASHBOARD_CHOICES).get(obj.dashboard_type, obj.dashboard_type)


class RoleConfigCreateSerializer(serializers.Serializer):
    """Création d'un rôle custom par un admin."""
    nom            = serializers.CharField(max_length=100)
    slug           = serializers.SlugField(max_length=30)
    dashboard_type = serializers.ChoiceField(choices=[c[0] for c in RoleConfig.DASHBOARD_CHOICES])
    permission_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )

    def validate_slug(self, value):
        request = self.context['request']
        restaurant = request.user.restaurant
        if RoleConfig.objects.filter(slug=value, restaurant=restaurant).exists():
            raise serializers.ValidationError("Un rôle avec ce slug existe déjà dans votre restaurant.")
        if RoleConfig.objects.filter(slug=value, is_system=True).exists():
            raise serializers.ValidationError("Ce slug est réservé à un rôle système.")
        return value

    def create(self, validated_data):
        request    = self.context['request']
        perm_ids   = validated_data.pop('permission_ids', [])
        role = RoleConfig.objects.create(
            restaurant=request.user.restaurant,
            is_system=False,
            **validated_data,
        )
        if perm_ids:
            perms = Permission.objects.filter(
                id__in=perm_ids,
            )
            role.permissions.set(perms)
        return role


class RoleConfigUpdateSerializer(serializers.Serializer):
    """Mise à jour partielle d'un rôle custom."""
    nom            = serializers.CharField(max_length=100, required=False)
    dashboard_type = serializers.ChoiceField(
        choices=[c[0] for c in RoleConfig.DASHBOARD_CHOICES], required=False
    )
    permission_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False
    )

    def update(self, instance, validated_data):
        perm_ids = validated_data.pop('permission_ids', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if perm_ids is not None:
            perms = Permission.objects.filter(id__in=perm_ids)
            instance.permissions.set(perms)
        return instance