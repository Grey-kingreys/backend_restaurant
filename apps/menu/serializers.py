# apps/menu/serializers.py
from rest_framework import serializers
from .models import Plat


class PlatListSerializer(serializers.ModelSerializer):
    """
    Serializer lecture allégé — liste des plats.
    - image retournée en URL absolue (build_absolute_uri).
    - prix_formate calculé côté serveur.
    - Pour les Tables : seuls les plats disponibles sont retournés (filtré en vue).
    - Pour Chef/Cuisinier/Admin/Manager : tous les plats.
    """
    image_url = serializers.SerializerMethodField()
    prix_formate = serializers.SerializerMethodField()
    categorie_display = serializers.SerializerMethodField()

    class Meta:
        model = Plat
        fields = [
            'id', 'nom', 'description', 'prix_unitaire', 'prix_formate',
            'image_url', 'disponible', 'categorie', 'categorie_display',
            'necessite_validation_cuisine', 'date_creation', 'date_modification',
        ]
        read_only_fields = ['id', 'date_creation', 'date_modification']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image:
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    def get_prix_formate(self, obj):
        return f"{obj.prix_unitaire:,.0f}".replace(',', ' ') + " GNF"

    def get_categorie_display(self, obj):
        return obj.get_categorie_display()


class PlatDetailSerializer(PlatListSerializer):
    """
    Serializer lecture détaillé — infos restaurant incluses.
    Même chose que PlatListSerializer avec le nom du restaurant.
    """
    restaurant_nom = serializers.SerializerMethodField()

    class Meta(PlatListSerializer.Meta):
        fields = PlatListSerializer.Meta.fields + ['restaurant_nom']

    def get_restaurant_nom(self, obj):
        return obj.restaurant.nom


class PlatCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer création / modification d'un plat.
    - Le champ `restaurant` est injecté depuis request.user.restaurant (ne jamais
      laisser le client le choisir — isolation SaaS).
    - L'image est optionnelle.
    - Validation : nom unique PAR restaurant (pas globalement).
    - Un plat ne peut JAMAIS être supprimé — toggle uniquement.
    """
    image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Plat
        fields = [
            'nom', 'description', 'prix_unitaire', 'categorie',
            'image', 'disponible', 'necessite_validation_cuisine',
        ]

    def validate_prix_unitaire(self, value):
        if value <= 0:
            raise serializers.ValidationError("Le prix doit être supérieur à 0.")
        return value

    def validate_nom(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Le nom ne peut pas être vide.")
        return value

    def validate_image(self, value):
        if value:
            # Max 5 MB
            if value.size > 5 * 1024 * 1024:
                raise serializers.ValidationError(
                    "L'image ne doit pas dépasser 5 Mo."
                )
            # Formats acceptés
            name_lower = value.name.lower()
            if not (name_lower.endswith('.jpg')
                    or name_lower.endswith('.jpeg')
                    or name_lower.endswith('.png')):
                raise serializers.ValidationError(
                    "Formats acceptés : JPG, JPEG, PNG."
                )
        return value

    def validate(self, data):
        """Unicité du nom de plat par restaurant."""
        request = self.context['request']
        restaurant = request.user.restaurant
        nom = data.get('nom', '')

        qs = Plat.objects.filter(
            restaurant=restaurant,
            nom__iexact=nom
        )
        # En modification : exclure l'instance courante
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError({
                'nom': f"Un plat nommé « {nom} » existe déjà dans ce restaurant."
            })
        return data

    def create(self, validated_data):
        """Restaurant injecté depuis le contexte — jamais depuis le payload."""
        request = self.context['request']
        validated_data['restaurant'] = request.user.restaurant
        return super().create(validated_data)

    def to_representation(self, instance):
        """Après create/update, retourner la représentation complète."""
        return PlatDetailSerializer(instance, context=self.context).data


class PlatToggleSerializer(serializers.Serializer):
    """
    Serializer pour l'endpoint toggle disponibilité.
    Pas de champ en entrée — action idempotente basée sur l'état courant.
    """
    pass