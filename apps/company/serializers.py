# apps/company/serializers.py
from rest_framework import serializers
from django.db import transaction
from django.contrib.auth import get_user_model

from .models import Restaurant, OnboardingToken
from .services.email_service import send_welcome_email

User = get_user_model()


class RestaurantSerializer(serializers.ModelSerializer):
    """
    Serializer lecture d'un restaurant.
    Inclut des compteurs utiles pour le Super Admin.
    """
    nombre_utilisateurs = serializers.SerializerMethodField()
    statut = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = [
            'id', 'nom', 'email_admin', 'telephone', 'adresse',
            'is_active', 'statut', 'nombre_utilisateurs',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_nombre_utilisateurs(self, obj):
        # Exclut les Rtable du compte — ce sont des comptes systeme
        return obj.users.filter(is_active=True).exclude(role='Rtable').count()

    def get_statut(self, obj):
        return "actif" if obj.is_active else "suspendu"


class RestaurantCreateSerializer(serializers.ModelSerializer):
    """
    Serializer creation d'un restaurant par le Super Admin.

    Workflow :
    1. Valide et cree le Restaurant
    2. Cree le compte Admin avec login = {slug}_admin
    3. Genere un OnboardingToken (48h)
    4. Envoie l'email de bienvenue via Resend
    5. Retourne le restaurant + les infos du compte Admin cree
    """

    class Meta:
        model = Restaurant
        fields = ['nom', 'email_admin', 'telephone', 'adresse']

    def validate_email_admin(self, value):
        """L'email doit etre unique — servira de login Admin."""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "Un utilisateur avec cet email existe deja."
            )
        return value

    def validate_nom(self, value):
        if Restaurant.objects.filter(nom__iexact=value).exists():
            raise serializers.ValidationError(
                "Un restaurant avec ce nom existe deja."
            )
        return value

    @transaction.atomic
    def create(self, validated_data):
        # 1. Creer le restaurant
        restaurant = Restaurant.objects.create(**validated_data)

        # 2. Generer le login Admin : {slug}_admin
        slug = restaurant.get_slug()
        login = f"{slug}_admin"

        # Garantir l'unicite du login (au cas ou deux restaurants ont le meme slug)
        base_login = login
        counter = 1
        while User.objects.filter(login=login).exists():
            login = f"{base_login}{counter}"
            counter += 1

        # 3. Creer le compte Admin
        admin_user = User.objects.create_user(
            login=login,
            password=None,  # Pas de mot de passe — l'Admin le definit via le token
            role='Radmin',
            restaurant=restaurant,
            email=restaurant.email_admin,
            nom_complet=f"Admin {restaurant.nom}",
            is_staff=True,
            must_change_password=True,
            actif=True,
        )
        # Desactiver le compte jusqu'a la premiere connexion via le token
        admin_user.is_active = False
        admin_user.save(update_fields=['is_active'])

        # 4. Generer le token d'onboarding
        onboarding_token = OnboardingToken.creer_pour(admin_user)

        # 5. Envoyer l'email de bienvenue
        email_ok = send_welcome_email(admin_user, restaurant, onboarding_token)
        if not email_ok:
            # On ne bloque pas la creation — on logue juste l'echec
            import logging
            logging.getLogger(__name__).warning(
                f"[Onboarding] Email non envoye pour {admin_user.email}"
            )

        # Stocker les infos admin pour la reponse (via context dans to_representation)
        restaurant._admin_login = admin_user.login
        restaurant._admin_email = admin_user.email
        restaurant._email_envoye = email_ok

        return restaurant

    def to_representation(self, instance):
        """Retourne la representation complete apres creation."""
        data = RestaurantSerializer(instance, context=self.context).data
        # Ajouter les infos du compte Admin cree
        data['admin_cree'] = {
            'login': getattr(instance, '_admin_login', None),
            'email': getattr(instance, '_admin_email', None),
            'email_bienvenue_envoye': getattr(instance, '_email_envoye', False),
            'note': (
                "L'Admin doit utiliser le lien envoye par email "
                "pour definir son mot de passe (valable 48h)."
            ),
        }
        return data


class RestaurantUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer mise a jour partielle d'un restaurant.
    Le Super Admin peut modifier les infos de base.
    """

    class Meta:
        model = Restaurant
        fields = ['nom', 'email_admin', 'telephone', 'adresse']


class OnboardingTokenValidateSerializer(serializers.Serializer):
    """
    Serializer validation du token de premiere connexion.
    Le frontend envoie le token + le nouveau mot de passe choisi par l'Admin.
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
            onboarding = OnboardingToken.objects.select_related('user').get(
                token=data['token']
            )
        except OnboardingToken.DoesNotExist:
            raise serializers.ValidationError({
                'token': "Token invalide ou inexistant."
            })
        if not onboarding.est_valide():
            raise serializers.ValidationError({
                'token': "Ce lien a expire ou a deja ete utilise."
            })
        data['onboarding'] = onboarding
        return data

    @transaction.atomic
    def save(self):
        onboarding = self.validated_data['onboarding']
        user = onboarding.user

        # Definir le mot de passe
        user.set_password(self.validated_data['password'])
        user.is_active = True
        user.must_change_password = False
        user.save(update_fields=['password', 'is_active', 'must_change_password'])

        # Invalider le token
        onboarding.utiliser()

        return user


class PlatformStatsSerializer(serializers.Serializer):
    """
    Serializer stats globales plateforme — Super Admin uniquement.
    Stub complet implementé en Phase 8 (dashboard/tasks.py + Celery).
    """
    restaurants_total = serializers.IntegerField()
    restaurants_actifs = serializers.IntegerField()
    restaurants_suspendus = serializers.IntegerField()
    utilisateurs_par_restaurant = serializers.ListField(
        child=serializers.DictField()
    )