# apps/paiements/schemas.py
# Serializers de documentation OpenAPI des vues paiements : ils décrivent les dicts
# construits à la main dans apps/paiements/api_views.py. Jamais utilisés à l'exécution.

from rest_framework import serializers

from .serializers import (
    CaisseGlobaleSerializer, CaisseComptableListSerializer,
    DemandeApprovisionnementSerializer, DepenseSerializer,
    RemiseServeurSerializer, PaiementSerializer,
)


class DashboardComptableDocSerializer(serializers.Serializer):
    """
    Réponse réelle de DashboardComptableView : les deux totaux sont des Decimal bruts
    placés dans un dict, que l'encodeur JSON de DRF sort en nombres (pas en texte).
    """
    caisse_globale_active = CaisseGlobaleSerializer(allow_null=True)
    ma_caisse_comptable = CaisseComptableListSerializer(allow_null=True)
    remises_en_attente_count = serializers.IntegerField()
    remises_validees_today = serializers.IntegerField()
    total_remises_today = serializers.FloatField()
    total_depenses_today = serializers.FloatField()


class CaissesGlobalesListeDocSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    caisses = CaisseGlobaleSerializer(many=True)


class CaissesComptablesListeDocSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    caisses = CaisseComptableListSerializer(many=True)


class DemandesApprovisionnementListeDocSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    demandes = DemandeApprovisionnementSerializer(many=True)


class DepensesListeDocSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    depenses = DepenseSerializer(many=True)


class RemisesListeDocSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    remises = RemiseServeurSerializer(many=True)


class PaiementsListeDocSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    paiements = PaiementSerializer(many=True)
