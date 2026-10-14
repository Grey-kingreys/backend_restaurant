# apps/company/schemas.py
# Serializers de documentation OpenAPI des vues company : ils décrivent les dicts
# construits à la main dans apps/company/api_views.py. Jamais utilisés à l'exécution.

from rest_framework import serializers

from .serializers import RestaurantSerializer


class RestaurantsPlateformeDocSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    restaurants = RestaurantSerializer(many=True)


class AdminCreeDocSerializer(serializers.Serializer):
    login = serializers.CharField()
    email = serializers.EmailField()
    email_bienvenue_envoye = serializers.BooleanField()
    note = serializers.CharField()


class RestaurantCreeDocSerializer(RestaurantSerializer):
    """Restaurant créé, avec les infos du compte Admin généré."""
    admin_cree = AdminCreeDocSerializer()

    class Meta(RestaurantSerializer.Meta):
        fields = RestaurantSerializer.Meta.fields + ['admin_cree']


class OnboardingActivationRequeteSerializer(serializers.Serializer):
    """Corps de l'activation : le token vient de l'URL, pas du corps."""
    password = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(write_only=True)


class OnboardingVerifieDocSerializer(serializers.Serializer):
    login = serializers.CharField()
    restaurant = serializers.CharField(help_text="Nom du restaurant.")
    expires_at = serializers.DateTimeField()


class OnboardingActiveDocSerializer(serializers.Serializer):
    login = serializers.CharField()
    restaurant = serializers.CharField(help_text="Nom du restaurant.")
    message = serializers.CharField()


class UtilisateursRestaurantDocSerializer(serializers.Serializer):
    restaurant_id = serializers.IntegerField()
    restaurant_nom = serializers.CharField()
    is_active = serializers.BooleanField()
    nombre_utilisateurs = serializers.IntegerField(help_text="Comptes actifs hors tables.")
    nombre_tables = serializers.IntegerField(help_text="Comptes table actifs.")


class StatsPlateformeDocSerializer(serializers.Serializer):
    restaurants_total = serializers.IntegerField()
    restaurants_actifs = serializers.IntegerField()
    restaurants_suspendus = serializers.IntegerField()
    utilisateurs_par_restaurant = UtilisateursRestaurantDocSerializer(many=True)
    _note = serializers.CharField()
