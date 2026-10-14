# apps/accounts/schemas.py
# Serializers de documentation OpenAPI des vues comptes : ils décrivent les dicts
# construits à la main dans apps/accounts/api_views.py et la vue SimpleJWT de
# rafraîchissement du jeton. Jamais utilisés à l'exécution.

from rest_framework import serializers

from .serializers import UserListSerializer, RoleConfigListSerializer, UserMeSerializer


class ConnexionDocSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="Jeton d'accès JWT.")
    refresh = serializers.CharField(help_text="Jeton de rafraîchissement JWT.")
    user = UserMeSerializer()


class RafraichirJetonRequeteSerializer(serializers.Serializer):
    refresh = serializers.CharField(help_text="Jeton de rafraîchissement JWT.")


class RafraichirJetonDocSerializer(serializers.Serializer):
    """Réponse de SimpleJWT, hors enveloppe : le refresh est renouvelé (rotation activée)."""
    access = serializers.CharField(help_text="Nouveau jeton d'accès JWT.")
    refresh = serializers.CharField(help_text="Nouveau jeton de rafraîchissement JWT.")


class UtilisateursListeDocSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    users = UserListSerializer(many=True)


class ReinitialisationConfirmeeDocSerializer(serializers.Serializer):
    login = serializers.CharField()


class RolesListeDocSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    roles = RoleConfigListSerializer(many=True)
