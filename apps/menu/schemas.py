# apps/menu/schemas.py
# Serializers de documentation OpenAPI des vues menu : ils décrivent les dicts
# construits à la main dans apps/menu/api_views.py. Jamais utilisés à l'exécution.

from rest_framework import serializers

from .serializers import PlatListSerializer


class PlatsListeDocSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    plats = PlatListSerializer(many=True)


class CategoriePlatDocSerializer(serializers.Serializer):
    value = serializers.CharField(help_text="Code de la catégorie, par exemple PLAT.")
    label = serializers.CharField(help_text="Libellé affichable.")


class CategoriesPlatDocSerializer(serializers.Serializer):
    categories = CategoriePlatDocSerializer(many=True)
