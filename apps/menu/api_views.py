# apps/menu/api_views.py
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import Plat
from .serializers import (
    PlatListSerializer,
    PlatDetailSerializer,
    PlatCreateUpdateSerializer,
)
from apps.accounts.permissions import (
    IsRestaurantActive,
    IsChefCuisinier,
    IsAdminOrManager,
    IsTable,
    IsCuisinierAny,
)


def success_response(data=None, message="", status_code=status.HTTP_200_OK):
    return Response(
        {"success": True, "data": data, "message": message},
        status=status_code
    )


def error_response(errors=None, message="", status_code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {"success": False, "errors": errors, "message": message},
        status=status_code
    )


def _get_base_queryset(request):
    """
    Retourne le queryset de base filtré par restaurant (isolation SaaS).
    Toujours filtré par request.user.restaurant.
    """
    return Plat.objects.filter(restaurant=request.user.restaurant)


class PlatListCreateView(APIView):
    """
    GET  /api/plats/  — Liste des plats
    POST /api/plats/  — Créer un plat (Chef / Admin / Manager)

    GET :
    - Rtable → uniquement les plats disponibles=True
    - Rchef_cuisinier, Rcuisinier, Radmin, Rmanager → tous les plats
    Filtres GET : ?categorie=PLAT, ?disponible=true/false, ?q=texte
    """
    permission_classes = [IsAuthenticated, IsRestaurantActive]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        summary="Lister les plats du restaurant",
        description=(
            "Retourne la liste des plats du restaurant connecté.\n\n"
            "- **Table** : uniquement les plats `disponible=True`\n"
            "- **Chef / Cuisinier / Admin / Manager** : tous les plats\n\n"
            "Filtres : `?categorie=PLAT`, `?disponible=true`, `?q=mot-clé`"
        ),
        parameters=[
            OpenApiParameter('categorie', OpenApiTypes.STR, description="ENTREE | PLAT | DESSERT | BOISSON | ACCOMPAGNEMENT"),
            OpenApiParameter('disponible', OpenApiTypes.BOOL, description="true / false"),
            OpenApiParameter('q', OpenApiTypes.STR, description="Recherche dans nom et description"),
        ],
        responses={200: PlatListSerializer(many=True)},
        tags=["Menu"],
    )
    def get(self, request):
        qs = _get_base_queryset(request)

        # Rtable → uniquement disponibles
        if request.user.is_table():
            qs = qs.filter(disponible=True)

        # Filtres optionnels
        categorie = request.query_params.get('categorie')
        if categorie:
            qs = qs.filter(categorie=categorie.upper())

        disponible = request.query_params.get('disponible')
        if disponible is not None and not request.user.is_table():
            qs = qs.filter(disponible=disponible.lower() == 'true')

        q = request.query_params.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(nom__icontains=q) | Q(description__icontains=q)
            )

        serializer = PlatListSerializer(qs, many=True, context={'request': request})
        return success_response(
            data={
                'count': qs.count(),
                'plats': serializer.data,
            },
            message="Liste des plats."
        )

    @extend_schema(
        summary="Créer un plat",
        description=(
            "Crée un nouveau plat dans le restaurant du créateur.\n\n"
            "- Accepte `multipart/form-data` pour l'upload d'image.\n"
            "- Le champ `restaurant` est injecté automatiquement — **ne pas l'envoyer**.\n"
            "- **Accès** : Chef Cuisinier, Admin, Manager."
        ),
        request=PlatCreateUpdateSerializer,
        responses={
            201: PlatDetailSerializer,
            400: OpenApiResponse(description="Données invalides"),
            403: OpenApiResponse(description="Accès refusé"),
        },
        tags=["Menu"],
    )
    def post(self, request):
        # Seuls Chef, Admin, Manager peuvent créer
        if not (request.user.is_chef_cuisinier()
                or request.user.is_admin()
                or request.user.is_manager()):
            return error_response(
                message="Seul le Chef Cuisinier, l'Administrateur ou le Manager peut créer un plat.",
                status_code=status.HTTP_403_FORBIDDEN
            )

        serializer = PlatCreateUpdateSerializer(
            data=request.data, context={'request': request}
        )
        if serializer.is_valid():
            plat = serializer.save()
            return success_response(
                data=serializer.to_representation(plat),
                message=f"Plat « {plat.nom} » créé avec succès.",
                status_code=status.HTTP_201_CREATED
            )
        return error_response(errors=serializer.errors, message="Données invalides.")


class PlatDetailView(APIView):
    """
    GET   /api/plats/<id>/  — Détail d'un plat
    PUT   /api/plats/<id>/  — Modifier un plat (Chef / Admin / Manager)
    PATCH /api/plats/<id>/  — Modification partielle
    (pas de DELETE — toggle uniquement)
    """
    permission_classes = [IsAuthenticated, IsRestaurantActive]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self, pk, request):
        return get_object_or_404(
            Plat,
            pk=pk,
            restaurant=request.user.restaurant
        )

    @extend_schema(
        summary="Détail d'un plat",
        responses={
            200: PlatDetailSerializer,
            404: OpenApiResponse(description="Plat introuvable ou hors restaurant"),
        },
        tags=["Menu"],
    )
    def get(self, request, pk):
        plat = self.get_object(pk, request)

        # Rtable ne voit que les plats disponibles
        if request.user.is_table() and not plat.disponible:
            return error_response(
                message="Ce plat n'est pas disponible.",
                status_code=status.HTTP_404_NOT_FOUND
            )

        serializer = PlatDetailSerializer(plat, context={'request': request})
        return success_response(data=serializer.data)

    @extend_schema(
        summary="Modifier un plat (complète)",
        request=PlatCreateUpdateSerializer,
        responses={
            200: PlatDetailSerializer,
            400: OpenApiResponse(description="Données invalides"),
            403: OpenApiResponse(description="Accès refusé"),
            404: OpenApiResponse(description="Plat introuvable"),
        },
        tags=["Menu"],
    )
    def put(self, request, pk):
        return self._update(request, pk, partial=False)

    @extend_schema(
        summary="Modifier un plat (partielle)",
        request=PlatCreateUpdateSerializer,
        responses={
            200: PlatDetailSerializer,
            400: OpenApiResponse(description="Données invalides"),
            403: OpenApiResponse(description="Accès refusé"),
            404: OpenApiResponse(description="Plat introuvable"),
        },
        tags=["Menu"],
    )
    def patch(self, request, pk):
        return self._update(request, pk, partial=True)

    def _update(self, request, pk, partial):
        if not (request.user.is_chef_cuisinier()
                or request.user.is_admin()
                or request.user.is_manager()):
            return error_response(
                message="Seul le Chef Cuisinier, l'Administrateur ou le Manager peut modifier un plat.",
                status_code=status.HTTP_403_FORBIDDEN
            )

        plat = self.get_object(pk, request)
        serializer = PlatCreateUpdateSerializer(
            plat, data=request.data, partial=partial, context={'request': request}
        )
        if serializer.is_valid():
            plat = serializer.save()
            return success_response(
                data=serializer.to_representation(plat),
                message=f"Plat « {plat.nom} » mis à jour."
            )
        return error_response(errors=serializer.errors, message="Données invalides.")


class PlatToggleView(APIView):
    """
    POST /api/plats/<id>/toggle/
    Active ou désactive un plat (inverse son état `disponible`).
    Un plat ne peut JAMAIS être supprimé — seulement désactivé.
    Accès : Chef Cuisinier, Admin, Manager.
    """
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    @extend_schema(
        summary="Activer / Désactiver un plat",
        description=(
            "Inverse l'état `disponible` du plat.\n\n"
            "Un plat ne peut **jamais** être supprimé, seulement désactivé.\n"
            "**Accès** : Chef Cuisinier, Admin, Manager."
        ),
        request=None,
        responses={
            200: PlatDetailSerializer,
            403: OpenApiResponse(description="Accès refusé"),
            404: OpenApiResponse(description="Plat introuvable"),
        },
        tags=["Menu"],
    )
    def post(self, request, pk):
        if not (request.user.is_chef_cuisinier()
                or request.user.is_admin()
                or request.user.is_manager()):
            return error_response(
                message="Seul le Chef Cuisinier, l'Administrateur ou le Manager peut activer/désactiver un plat.",
                status_code=status.HTTP_403_FORBIDDEN
            )

        plat = get_object_or_404(
            Plat, pk=pk, restaurant=request.user.restaurant
        )
        plat.toggle_disponibilite()

        statut = "disponible" if plat.disponible else "indisponible"
        serializer = PlatDetailSerializer(plat, context={'request': request})
        return success_response(
            data=serializer.data,
            message=f"Plat « {plat.nom} » est maintenant {statut}."
        )


class PlatCategoriesView(APIView):
    """
    GET /api/plats/categories/
    Retourne la liste des catégories disponibles.
    Accès : tous les rôles authentifiés.
    """
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    @extend_schema(
        summary="Lister les catégories de plats",
        description="Retourne toutes les catégories disponibles avec leurs libellés.",
        responses={200: OpenApiResponse(description="Liste des catégories")},
        tags=["Menu"],
    )
    def get(self, request):
        categories = [
            {'value': value, 'label': label}
            for value, label in Plat.CATEGORIE_CHOICES
        ]
        return success_response(
            data={'categories': categories},
            message="Catégories disponibles."
        )