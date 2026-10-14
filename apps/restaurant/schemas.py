# apps/restaurant/schemas.py
# Serializers de documentation OpenAPI des vues restaurant : ils décrivent les corps
# de requête lus à la main et les dicts renvoyés par apps/restaurant/api_views.py.
# Jamais utilisés à l'exécution.

from rest_framework import serializers

from apps.accounts.serializers import UserMeSerializer


class QRLoginRequeteSerializer(serializers.Serializer):
    lat = serializers.FloatField(
        required=False, help_text="Latitude du client, requise si le restaurant a des coordonnées GPS.",
    )
    lng = serializers.FloatField(
        required=False, help_text="Longitude du client, requise si le restaurant a des coordonnées GPS.",
    )


class QRLoginDocSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="Jeton d'accès JWT.")
    refresh = serializers.CharField(help_text="Jeton de rafraîchissement JWT.")
    user = UserMeSerializer()
    session_token = serializers.CharField(help_text="Jeton de la session table créée.")
    table_login = serializers.CharField()
    restaurant = serializers.CharField(allow_null=True, help_text="Nom du restaurant.")
    expires_at = serializers.DateTimeField(help_text="Fin de la session table.")
