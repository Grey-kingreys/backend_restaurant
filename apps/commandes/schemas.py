# apps/commandes/schemas.py
# Serializers de documentation OpenAPI des vues commandes : ils décrivent les corps
# de requête lus à la main et les dicts renvoyés par apps/commandes/api_views.py.
# Jamais utilisés à l'exécution.

from rest_framework import serializers

from .serializers import (
    PanierItemSerializer, CommandeDetailSerializer, CommandeListSerializer,
    CommandeCuisinierSerializer,
)


# ── Requêtes ─────────────────────────────────────────────────────────────────

class PanierQuantiteRequeteSerializer(serializers.Serializer):
    quantite = serializers.IntegerField(min_value=1, max_value=10)


class CommandeServeurArticleRequeteSerializer(serializers.Serializer):
    plat_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1, max_value=50)


class CommandeServeurRequeteSerializer(serializers.Serializer):
    """Corps de la prise de commande par le staff (mêmes champs que CommandeServeurCreateSerializer)."""
    type_commande = serializers.ChoiceField(
        choices=['sur_table', 'livraison', 'emporter'], required=False, default='sur_table',
    )
    table_id = serializers.IntegerField(
        required=False, allow_null=True,
        help_text="Identifiant de la table du restaurant, requis pour une commande sur place.",
    )
    client_nom = serializers.CharField(required=False, allow_blank=True, max_length=150)
    client_telephone = serializers.CharField(
        required=False, allow_blank=True, max_length=20,
        help_text="Requis pour une livraison.",
    )
    client_adresse_livraison = serializers.CharField(
        required=False, allow_blank=True,
        help_text="Adresse en texte libre, requise pour une livraison.",
    )
    items = CommandeServeurArticleRequeteSerializer(many=True, allow_empty=False)


class AnnulerCommandeStaffRequeteSerializer(serializers.Serializer):
    motif = serializers.CharField(help_text="Motif d'annulation, obligatoire.")


# ── Réponses ─────────────────────────────────────────────────────────────────

class PanierDocSerializer(serializers.Serializer):
    items = PanierItemSerializer(many=True)
    nb_items = serializers.IntegerField()
    montant_total = serializers.CharField(help_text="Décimal en texte.")


class PanierViderDocSerializer(serializers.Serializer):
    supprimés = serializers.IntegerField(help_text="Nombre de lignes du panier supprimées.")


class CommandesDetailListeDocSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    commandes = CommandeDetailSerializer(many=True)


class CommandesListeDocSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    commandes = CommandeListSerializer(many=True)


class CommandesCuisineDocSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    commandes = CommandeCuisinierSerializer(many=True)


class LivraisonLienDocSerializer(serializers.Serializer):
    qr_code_url = serializers.CharField(help_text="Image PNG du QR Code en data URL base64.")
    lien = serializers.CharField(help_text="URL publique du suivi de livraison.")
    token = serializers.CharField(help_text="Jeton du lien de livraison.")
