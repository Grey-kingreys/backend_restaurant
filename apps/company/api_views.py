# apps/company/api_views.py
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import Restaurant, OnboardingToken
from .permissions import IsSuperAdmin
from .serializers import (
    RestaurantSerializer,
    RestaurantCreateSerializer,
    RestaurantUpdateSerializer,
    OnboardingTokenValidateSerializer,
    PlatformStatsSerializer,
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


# ─────────────────────────────────────────────────────────────────────────────
# CRUD RESTAURANTS — Super Admin
# ─────────────────────────────────────────────────────────────────────────────

class RestaurantListCreateView(APIView):
    """
    GET  /api/company/restaurants/  — Liste tous les restaurants
    POST /api/company/restaurants/  — Creer un restaurant + Admin + email
    Acces : Super Admin uniquement
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        summary="Lister tous les restaurants",
        description="Retourne la liste complète de tous les restaurants de la plateforme. Accès Super Admin uniquement.",
        responses={
            200: RestaurantSerializer(many=True),
            403: OpenApiResponse(description="Accès refusé — Super Admin requis"),
        },
        tags=["Restaurants"],
    )
    def get(self, request):
        restaurants = Restaurant.objects.all().order_by('nom')
        serializer = RestaurantSerializer(
            restaurants, many=True, context={'request': request}
        )
        return success_response(
            data={
                'count': restaurants.count(),
                'restaurants': serializer.data,
            },
            message="Liste des restaurants"
        )

    @extend_schema(
        summary="Créer un restaurant + compte Admin",
        description=(
            "Crée un nouveau restaurant et génère automatiquement :\n"
            "- Un compte Admin avec login `{slug}_admin`\n"
            "- Un token d'onboarding valable 48h\n"
            "- Un email de bienvenue envoyé à l'adresse fournie\n\n"
            "Accès Super Admin uniquement."
        ),
        request=RestaurantCreateSerializer,
        responses={
            201: RestaurantSerializer,
            400: OpenApiResponse(description="Données invalides (nom déjà pris, email déjà utilisé, etc.)"),
            403: OpenApiResponse(description="Accès refusé — Super Admin requis"),
        },
        tags=["Restaurants"],
    )
    def post(self, request):
        serializer = RestaurantCreateSerializer(
            data=request.data, context={'request': request}
        )
        if serializer.is_valid():
            restaurant = serializer.save()
            return success_response(
                data=serializer.to_representation(restaurant),
                message="Restaurant cree avec succes. Un email de bienvenue a ete envoye a l'administrateur.",
                status_code=status.HTTP_201_CREATED
            )
        return error_response(
            errors=serializer.errors,
            message="Donnees invalides."
        )


class RestaurantDetailView(APIView):
    """
    GET    /api/company/restaurants/<id>/  — Detail d'un restaurant
    PATCH  /api/company/restaurants/<id>/  — Modifier les infos
    Acces : Super Admin uniquement
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_object(self, pk):
        return get_object_or_404(Restaurant, pk=pk)

    @extend_schema(
        summary="Détail d'un restaurant",
        description="Retourne les informations complètes d'un restaurant par son ID.",
        responses={
            200: RestaurantSerializer,
            403: OpenApiResponse(description="Accès refusé — Super Admin requis"),
            404: OpenApiResponse(description="Restaurant introuvable"),
        },
        tags=["Restaurants"],
    )
    def get(self, request, pk):
        restaurant = self.get_object(pk)
        serializer = RestaurantSerializer(restaurant, context={'request': request})
        return success_response(data=serializer.data)

    @extend_schema(
        summary="Modifier un restaurant",
        description="Mise à jour partielle des informations d'un restaurant (nom, email, téléphone, adresse).",
        request=RestaurantUpdateSerializer,
        responses={
            200: RestaurantSerializer,
            400: OpenApiResponse(description="Données invalides"),
            403: OpenApiResponse(description="Accès refusé — Super Admin requis"),
            404: OpenApiResponse(description="Restaurant introuvable"),
        },
        tags=["Restaurants"],
    )
    def patch(self, request, pk):
        restaurant = self.get_object(pk)
        serializer = RestaurantUpdateSerializer(
            restaurant, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return success_response(
                data=RestaurantSerializer(restaurant, context={'request': request}).data,
                message="Restaurant mis a jour."
            )
        return error_response(errors=serializer.errors, message="Donnees invalides.")


class RestaurantSuspendView(APIView):
    """
    POST /api/company/restaurants/<id>/suspend/
    Suspend le restaurant — bloque tous les acces.
    Acces : Super Admin uniquement
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        summary="Suspendre un restaurant",
        description=(
            "Suspend le restaurant — tous les accès des utilisateurs de ce restaurant "
            "seront bloqués immédiatement. L'opération est réversible via `/activate/`."
        ),
        request=None,
        responses={
            200: RestaurantSerializer,
            400: OpenApiResponse(description="Restaurant déjà suspendu"),
            403: OpenApiResponse(description="Accès refusé — Super Admin requis"),
            404: OpenApiResponse(description="Restaurant introuvable"),
        },
        tags=["Restaurants"],
    )
    def post(self, request, pk):
        restaurant = get_object_or_404(Restaurant, pk=pk)
        if not restaurant.is_active:
            return error_response(
                message="Ce restaurant est deja suspendu."
            )
        restaurant.suspendre()
        return success_response(
            data=RestaurantSerializer(restaurant, context={'request': request}).data,
            message=f"Restaurant '{restaurant.nom}' suspendu."
        )


class RestaurantActivateView(APIView):
    """
    POST /api/company/restaurants/<id>/activate/
    Reactiver un restaurant suspendu.
    Acces : Super Admin uniquement
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        summary="Réactiver un restaurant suspendu",
        description="Réactive un restaurant précédemment suspendu. Les accès utilisateurs sont rétablis immédiatement.",
        request=None,
        responses={
            200: RestaurantSerializer,
            400: OpenApiResponse(description="Restaurant déjà actif"),
            403: OpenApiResponse(description="Accès refusé — Super Admin requis"),
            404: OpenApiResponse(description="Restaurant introuvable"),
        },
        tags=["Restaurants"],
    )
    def post(self, request, pk):
        restaurant = get_object_or_404(Restaurant, pk=pk)
        if restaurant.is_active:
            return error_response(
                message="Ce restaurant est deja actif."
            )
        restaurant.reactiver()
        return success_response(
            data=RestaurantSerializer(restaurant, context={'request': request}).data,
            message=f"Restaurant '{restaurant.nom}' reactive."
        )


# ─────────────────────────────────────────────────────────────────────────────
# ONBOARDING — Validation du token de premiere connexion
# ─────────────────────────────────────────────────────────────────────────────

class OnboardingValidateView(APIView):
    """
    GET  /api/company/onboarding/<token>/  — Verifier si le token est valide
    POST /api/company/onboarding/<token>/  — Definir le mot de passe + activer le compte

    Acces : Public (pas de JWT requis — c'est la premiere connexion)
    """
    permission_classes = []  # Public

    @extend_schema(
        summary="Vérifier la validité d'un token d'onboarding",
        description=(
            "Vérifie si le token est valide sans le consommer. "
            "Appelé par le frontend au chargement de la page `/auth/first-login?token=<uuid>` "
            "pour afficher le formulaire ou un message d'erreur. Accès public."
        ),
        responses={
            200: OpenApiResponse(description="Token valide — retourne login et nom du restaurant"),
            404: OpenApiResponse(description="Token inexistant"),
            410: OpenApiResponse(description="Token expiré ou déjà utilisé"),
        },
        tags=["Onboarding"],
    )
    def get(self, request, token):
        """Verifier la validite du token sans le consommer."""
        try:
            onboarding = OnboardingToken.objects.select_related(
                'user', 'user__restaurant'
            ).get(token=token)
        except OnboardingToken.DoesNotExist:
            return error_response(
                message="Token invalide ou inexistant.",
                status_code=status.HTTP_404_NOT_FOUND
            )

        if not onboarding.est_valide():
            return error_response(
                message="Ce lien a expire ou a deja ete utilise.",
                status_code=status.HTTP_410_GONE
            )

        return success_response(
            data={
                'login': onboarding.user.login,
                'restaurant': onboarding.user.restaurant.nom,
                'expires_at': onboarding.expires_at,
            },
            message="Token valide."
        )

    @extend_schema(
        summary="Définir le mot de passe via token d'onboarding",
        description=(
            "Consomme le token et active le compte Admin. "
            "L'Admin choisit son mot de passe lors de sa toute première connexion. "
            "Après cette opération, le token devient inutilisable. Accès public."
        ),
        request=OnboardingTokenValidateSerializer,
        responses={
            200: OpenApiResponse(description="Compte activé — l'Admin peut maintenant se connecter"),
            400: OpenApiResponse(description="Token invalide, expiré ou mots de passe non concordants"),
        },
        tags=["Onboarding"],
    )
    def post(self, request, token):
        """Definir le mot de passe et activer le compte Admin."""
        data = request.data.copy()
        data['token'] = str(token)

        serializer = OnboardingTokenValidateSerializer(data=data)
        if serializer.is_valid():
            user = serializer.save()
            return success_response(
                data={
                    'login': user.login,
                    'restaurant': user.restaurant.nom,
                    'message': (
                        "Mot de passe defini avec succes. "
                        "Vous pouvez maintenant vous connecter."
                    ),
                },
                message="Compte active avec succes.",
                status_code=status.HTTP_200_OK
            )
        return error_response(
            errors=serializer.errors,
            message="Donnees invalides."
        )


# ─────────────────────────────────────────────────────────────────────────────
# STATS GLOBALES — Super Admin
# ─────────────────────────────────────────────────────────────────────────────

class PlatformStatsView(APIView):
    """
    GET /api/company/stats/
    Stats globales de la plateforme — Super Admin uniquement.
    Implementation complete en Phase 8 (dashboard/tasks.py).
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        summary="Statistiques globales de la plateforme",
        description=(
            "Retourne les statistiques globales : nombre de restaurants actifs/suspendus, "
            "nombre d'utilisateurs et de tables par restaurant. "
            "Les statistiques détaillées (commandes, revenus) seront disponibles en Phase 8. "
            "Accès Super Admin uniquement."
        ),
        responses={
            200: PlatformStatsSerializer,
            403: OpenApiResponse(description="Accès refusé — Super Admin requis"),
        },
        tags=["Stats"],
    )
    def get(self, request):
        from django.contrib.auth import get_user_model
        from apps.commandes.models import Commande
        from apps.menu.models import Plat

        User = get_user_model()

        restaurants = Restaurant.objects.all()
        actifs = restaurants.filter(is_active=True)
        suspendus = restaurants.filter(is_active=False)

        utilisateurs_par_restaurant = []
        for r in restaurants:
            utilisateurs_par_restaurant.append({
                'restaurant_id': r.id,
                'restaurant_nom': r.nom,
                'is_active': r.is_active,
                'nombre_utilisateurs': r.users.filter(
                    is_active=True
                ).exclude(role='Rtable').count(),
                'nombre_tables': r.users.filter(
                    is_active=True, role='Rtable'
                ).count(),
            })

        data = {
            'restaurants_total': restaurants.count(),
            'restaurants_actifs': actifs.count(),
            'restaurants_suspendus': suspendus.count(),
            'utilisateurs_par_restaurant': utilisateurs_par_restaurant,
            '_note': (
                "Les statistiques detaillees (commandes, revenus, plats) "
                "seront disponibles en Phase 8 via /api/v1/dashboard/super/stats/"
            ),
        }

        return success_response(
            data=data,
            message="Statistiques globales de la plateforme."
        )