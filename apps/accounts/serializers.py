# apps/accounts/serializers.py
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.db import transaction

from .models import User, PasswordResetToken
from .services.email_service import send_password_reset_email


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

        # Vérification restaurant actif (sauf Super Admin)
        if not user.is_super_admin():
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
    statut = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'login', 'role', 'nom_complet', 'email', 'telephone',
            'restaurant', 'restaurant_nom', 'actif', 'statut',
            'must_change_password', 'date_creation',
        ]
        read_only_fields = fields

    def get_restaurant_nom(self, obj):
        return obj.restaurant.nom if obj.restaurant else None

    def get_statut(self, obj):
        return "actif" if obj.actif else "inactif"


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
    password = serializers.CharField(write_only=True, min_length=8, required=False)

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