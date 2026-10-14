# apps/restaurant/schemas.py
# Serializers de documentation OpenAPI des vues restaurant : ils décrivent les corps
# de requête lus à la main et les dicts renvoyés par apps/restaurant/api_views.py.
# Jamais utilisés à l'exécution.

from rest_framework import serializers

from apps.accounts.serializers import UserMeSerializer
from apps.commandes.serializers import CommandeListSerializer
from .serializers import TableRestaurantListSerializer


# ── Requêtes ─────────────────────────────────────────────────────────────────

class QRLoginRequeteSerializer(serializers.Serializer):
    lat = serializers.FloatField(
        required=False, help_text="Latitude du client, requise si le restaurant a des coordonnées GPS.",
    )
    lng = serializers.FloatField(
        required=False, help_text="Longitude du client, requise si le restaurant a des coordonnées GPS.",
    )


class PositionGpsRequeteSerializer(serializers.Serializer):
    lat = serializers.FloatField(required=False, help_text="Latitude de la table, si le GPS est disponible.")
    lng = serializers.FloatField(required=False, help_text="Longitude de la table, si le GPS est disponible.")


class ReservationReaffecterRequeteSerializer(serializers.Serializer):
    table_id = serializers.IntegerField(help_text="Identifiant de la table du restaurant à attribuer.")


class ReservationBloquerRequeteSerializer(serializers.Serializer):
    raison = serializers.CharField(
        required=False, allow_blank=True, max_length=255,
        help_text="Raison du blocage, tronquée à 255 caractères.",
    )


# ── Réponses ─────────────────────────────────────────────────────────────────

class QRLoginDocSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="Jeton d'accès JWT.")
    refresh = serializers.CharField(help_text="Jeton de rafraîchissement JWT.")
    user = UserMeSerializer()
    session_token = serializers.CharField(help_text="Jeton de la session table créée.")
    table_login = serializers.CharField()
    restaurant = serializers.CharField(allow_null=True, help_text="Nom du restaurant.")
    expires_at = serializers.DateTimeField(help_text="Fin de la session table.")


class TablesListeDocSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    tables = TableRestaurantListSerializer(many=True)


class QRInfoDocSerializer(serializers.Serializer):
    """Sans QR Code généré, seul `a_qr_code` (false) est renvoyé."""
    a_qr_code = serializers.BooleanField()
    qr_code_url = serializers.CharField(required=False, help_text="Image PNG du QR Code en data URL base64.")
    qr_login_url = serializers.CharField(required=False, help_text="URL de connexion encodée dans le QR Code.")
    table = serializers.CharField(required=False, help_text="Numéro de la table.")


class QRGenererDocSerializer(serializers.Serializer):
    qr_code_url = serializers.CharField(help_text="Image PNG du QR Code en data URL base64.")
    qr_login_url = serializers.CharField(help_text="URL de connexion encodée dans le QR Code.")
    table = serializers.CharField(help_text="Numéro de la table.")


class PositionStatutDocSerializer(serializers.Serializer):
    """Les clés présentes dépendent de `status`."""
    status = serializers.ChoiceField(
        choices=['ok', 'out_of_range', 'expired_warn', 'expired', 'all_paid', 'no_session'],
    )
    disconnect = serializers.BooleanField(required=False, help_text="Pour out_of_range : déconnecter la table.")
    strikes = serializers.IntegerField(required=False, help_text="Pour out_of_range sans déconnexion : nombre d'échecs.")
    message = serializers.CharField(required=False)
    paid_at = serializers.CharField(
        required=False, allow_null=True, help_text="Date ISO du paiement (expired, all_paid).",
    )
    expires_at = serializers.CharField(
        required=False, allow_null=True, help_text="Date ISO de fin de session (ok).",
    )
    minutes_remaining = serializers.IntegerField(
        required=False, allow_null=True, help_text="Minutes avant expiration (ok).",
    )


class DistanceStatutDocSerializer(serializers.Serializer):
    in_range = serializers.BooleanField()
    distance = serializers.IntegerField(required=False, help_text="Distance au restaurant en mètres.")
    message = serializers.CharField(required=False)


class DashboardServeurTableDocSerializer(serializers.Serializer):
    table_id = serializers.IntegerField()
    numero_table = serializers.CharField()
    nombre_places = serializers.IntegerField()
    table_login = serializers.CharField()
    statut = serializers.CharField(help_text="libre | en_attente | prete | servie")
    nb_commandes_actives = serializers.IntegerField()
    commandes = CommandeListSerializer(many=True)


class DashboardServeurStatsDocSerializer(serializers.Serializer):
    total_tables = serializers.IntegerField()
    libres = serializers.IntegerField()
    en_attente = serializers.IntegerField()
    pretes = serializers.IntegerField()
    servies = serializers.IntegerField()
    commandes_actives_total = serializers.IntegerField()


class DashboardServeurDocSerializer(serializers.Serializer):
    tables = DashboardServeurTableDocSerializer(many=True)
    stats = DashboardServeurStatsDocSerializer()


class ReservationStaffDocSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    client_id = serializers.IntegerField()
    table_numero = serializers.CharField(allow_null=True)
    table_places = serializers.IntegerField(allow_null=True)
    client_nom = serializers.CharField()
    client_telephone = serializers.CharField(allow_null=True)
    client_email = serializers.EmailField(allow_null=True)
    date_reservation = serializers.DateField()
    heure = serializers.CharField(help_text="Format HH:MM.")
    heure_fin = serializers.CharField(help_text="Format HH:MM.")
    duree_minutes = serializers.IntegerField()
    nombre_personnes = serializers.IntegerField()
    note = serializers.CharField()
    statut = serializers.CharField()
    statut_label = serializers.CharField()
    no_show_count = serializers.IntegerField()
    client_a_risque = serializers.BooleanField()
    client_bloque = serializers.BooleanField()
    date_creation = serializers.DateTimeField()


class ReservationsStaffListeDocSerializer(serializers.Serializer):
    reservations = ReservationStaffDocSerializer(many=True)
    count = serializers.IntegerField()
