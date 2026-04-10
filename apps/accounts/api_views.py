# apps/accounts/api_views.py
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import User
from .permissions import IsAdminOrManager, IsAdmin, IsRestaurantActive, IsSameRestaurant
from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    UserMeSerializer,
    UserListSerializer,
    UserDetailSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    AdminPasswordResetSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    ChangePasswordSerializer,
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
# AUTH
# ─────────────────────────────────────────────────────────────────────────────

class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Connexion",
        description=(
            "Connexion unifiée :\n"
            "- **Staff** (Admin, Manager, Serveur…) : `email` + `password`\n"
            "- **Table** : `login` + `password` (via QR Code ou formulaire)\n\n"
            "Retourne `access` + `refresh` + payload enrichi (`role`, `nom_complet`, `restaurant_id`)."
        ),
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(description="Tokens JWT + infos utilisateur"),
            400: OpenApiResponse(description="Identifiants invalides"),
        },
        tags=["Auth"],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.validated_data['user']
            tokens = serializer.get_tokens(user)
            return success_response(
                data={
                    **tokens,
                    'user': UserMeSerializer(user).data,
                },
                message="Connexion réussie."
            )
        return error_response(
            errors=serializer.errors,
            message="Identifiants invalides."
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Déconnexion",
        description="Blackliste le refresh token. L'access token reste valide jusqu'à son expiration naturelle.",
        request=LogoutSerializer,
        responses={
            200: OpenApiResponse(description="Déconnexion réussie"),
            400: OpenApiResponse(description="Token invalide"),
        },
        tags=["Auth"],
    )
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return success_response(message="Déconnexion réussie.")
        return error_response(errors=serializer.errors)


class MeView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    @extend_schema(
        summary="Profil de l'utilisateur connecté",
        description="Retourne les informations complètes de l'utilisateur authentifié.",
        responses={
            200: UserMeSerializer,
            401: OpenApiResponse(description="Non authentifié"),
        },
        tags=["Auth"],
    )
    def get(self, request):
        serializer = UserMeSerializer(request.user)
        return success_response(data=serializer.data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Changer son mot de passe",
        description=(
            "Permet à l'utilisateur connecté de changer son mot de passe.\n"
            "Utilisé aussi pour le **first-login** quand `must_change_password=True`."
        ),
        request=ChangePasswordSerializer,
        responses={
            200: OpenApiResponse(description="Mot de passe modifié"),
            400: OpenApiResponse(description="Ancien mot de passe incorrect ou mots de passe non concordants"),
        },
        tags=["Auth"],
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return success_response(message="Mot de passe modifié avec succès.")
        return error_response(errors=serializer.errors)


# ─────────────────────────────────────────────────────────────────────────────
# CRUD UTILISATEURS
# ─────────────────────────────────────────────────────────────────────────────

class UserListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrManager, IsRestaurantActive]

    @extend_schema(
        summary="Lister les utilisateurs du restaurant",
        description=(
            "Retourne la liste paginée des utilisateurs du restaurant connecté.\n"
            "Filtres disponibles : `?role=Rserveur`, `?actif=true`"
        ),
        responses={
            200: UserListSerializer(many=True),
            403: OpenApiResponse(description="Accès réservé Admin/Manager"),
        },
        tags=["Utilisateurs"],
    )
    def get(self, request):
        qs = User.objects.filter(
            restaurant=request.user.restaurant
        ).exclude(role='Rsuper_admin').order_by('role', 'nom_complet')

        # Filtres optionnels
        role = request.query_params.get('role')
        actif = request.query_params.get('actif')
        if role:
            qs = qs.filter(role=role)
        if actif is not None:
            qs = qs.filter(actif=actif.lower() == 'true')

        serializer = UserListSerializer(qs, many=True)
        return success_response(
            data={
                'count': qs.count(),
                'users': serializer.data,
            },
            message="Liste des utilisateurs."
        )

    @extend_schema(
        summary="Créer un utilisateur",
        description=(
            "Crée un utilisateur dans le restaurant du créateur.\n\n"
            "- Le **login** est généré automatiquement (`{slug}_{role}_{n}`)\n"
            "- `must_change_password` est forcé à `True`\n"
            "- Seul l'**Admin** peut créer un `Radmin` ou `Rmanager`\n"
            "- L'**email** est obligatoire pour tous les rôles sauf `Rtable`"
        ),
        request=UserCreateSerializer,
        responses={
            201: UserDetailSerializer,
            400: OpenApiResponse(description="Données invalides"),
            403: OpenApiResponse(description="Accès réservé Admin/Manager"),
        },
        tags=["Utilisateurs"],
    )
    def post(self, request):
        serializer = UserCreateSerializer(
            data=request.data, context={'request': request}
        )
        if serializer.is_valid():
            user = serializer.save()
            return success_response(
                data=UserDetailSerializer(user).data,
                message=f"Utilisateur '{user.login}' créé avec succès.",
                status_code=status.HTTP_201_CREATED
            )
        return error_response(errors=serializer.errors, message="Données invalides.")


class UserDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrManager, IsRestaurantActive]

    def get_object(self, pk, request):
        user = get_object_or_404(
            User,
            pk=pk,
            restaurant=request.user.restaurant
        )
        return user

    @extend_schema(
        summary="Détail d'un utilisateur",
        responses={
            200: UserDetailSerializer,
            403: OpenApiResponse(description="Accès réservé Admin/Manager"),
            404: OpenApiResponse(description="Utilisateur introuvable"),
        },
        tags=["Utilisateurs"],
    )
    def get(self, request, pk):
        user = self.get_object(pk, request)
        return success_response(data=UserDetailSerializer(user).data)

    @extend_schema(
        summary="Modifier un utilisateur",
        description="Mise à jour partielle (nom, email, téléphone, rôle). Seul l'Admin peut modifier le rôle vers Admin/Manager.",
        request=UserUpdateSerializer,
        responses={
            200: UserDetailSerializer,
            400: OpenApiResponse(description="Données invalides"),
            403: OpenApiResponse(description="Accès réservé Admin/Manager"),
            404: OpenApiResponse(description="Utilisateur introuvable"),
        },
        tags=["Utilisateurs"],
    )
    def patch(self, request, pk):
        user = self.get_object(pk, request)
        serializer = UserUpdateSerializer(
            user, data=request.data, partial=True, context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return success_response(
                data=UserDetailSerializer(user).data,
                message="Utilisateur mis à jour."
            )
        return error_response(errors=serializer.errors, message="Données invalides.")

    @extend_schema(
        summary="Supprimer un utilisateur",
        description=(
            "Suppression définitive. **Accès Admin uniquement.**\n\n"
            "- Un Admin ne peut pas se supprimer lui-même\n"
            "- Le Super Admin ne peut pas être supprimé via cette route"
        ),
        responses={
            200: OpenApiResponse(description="Utilisateur supprimé"),
            400: OpenApiResponse(description="Suppression impossible"),
            403: OpenApiResponse(description="Accès réservé à l'Administrateur"),
            404: OpenApiResponse(description="Utilisateur introuvable"),
        },
        tags=["Utilisateurs"],
    )
    def delete(self, request, pk):
        # Suppression réservée à l'Admin uniquement (pas Manager)
        if not request.user.is_admin():
            return error_response(
                message="Seul l'Administrateur peut supprimer un utilisateur.",
                status_code=status.HTTP_403_FORBIDDEN
            )
        user = self.get_object(pk, request)
        if user == request.user:
            return error_response(
                message="Vous ne pouvez pas supprimer votre propre compte."
            )
        login = user.login
        user.delete()
        return success_response(message=f"Utilisateur '{login}' supprimé.")


class UserToggleView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrManager, IsRestaurantActive]

    @extend_schema(
        summary="Activer / Désactiver un utilisateur",
        description=(
            "Bascule l'état `actif` de l'utilisateur.\n"
            "Un utilisateur désactivé ne peut plus se connecter."
        ),
        request=None,
        responses={
            200: UserDetailSerializer,
            400: OpenApiResponse(description="Impossible de désactiver son propre compte"),
            403: OpenApiResponse(description="Accès réservé Admin/Manager"),
            404: OpenApiResponse(description="Utilisateur introuvable"),
        },
        tags=["Utilisateurs"],
    )
    def post(self, request, pk):
        user = get_object_or_404(
            User, pk=pk, restaurant=request.user.restaurant
        )
        if user == request.user:
            return error_response(
                message="Vous ne pouvez pas désactiver votre propre compte."
            )
        user.actif = not user.actif
        user.save(update_fields=['actif'])
        statut = "activé" if user.actif else "désactivé"
        return success_response(
            data=UserDetailSerializer(user).data,
            message=f"Utilisateur '{user.login}' {statut}."
        )


# ─────────────────────────────────────────────────────────────────────────────
# RESET MOT DE PASSE
# ─────────────────────────────────────────────────────────────────────────────

class AdminPasswordResetView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrManager, IsRestaurantActive]

    @extend_schema(
        summary="Réinitialiser le mot de passe d'un utilisateur (Admin)",
        description=(
            "L'Admin ou Manager définit un nouveau mot de passe pour un utilisateur.\n"
            "`must_change_password` est automatiquement remis à `True` — "
            "l'utilisateur devra changer son mot de passe à sa prochaine connexion."
        ),
        request=AdminPasswordResetSerializer,
        responses={
            200: OpenApiResponse(description="Mot de passe réinitialisé"),
            403: OpenApiResponse(description="Accès réservé Admin/Manager"),
            404: OpenApiResponse(description="Utilisateur introuvable"),
        },
        tags=["Utilisateurs"],
    )
    def post(self, request, pk):
        user = get_object_or_404(
            User, pk=pk, restaurant=request.user.restaurant
        )
        serializer = AdminPasswordResetSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user)
            return success_response(
                message=f"Mot de passe de '{user.login}' réinitialisé. "
                        "L'utilisateur devra le changer à sa prochaine connexion."
            )
        return error_response(errors=serializer.errors)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Demander une réinitialisation de mot de passe",
        description=(
            "L'utilisateur soumet son **email** pour recevoir un lien de réinitialisation.\n\n"
            "La réponse est toujours identique (succès) pour éviter l'énumération d'emails.\n"
            "Le lien envoyé redirige vers : `{FRONTEND_URL}/auth/reset-password?token=<uuid>`\n"
            "Le token est valable **1 heure**."
        ),
        request=PasswordResetRequestSerializer,
        responses={
            200: OpenApiResponse(description="Email envoyé si l'adresse existe"),
        },
        tags=["Mot de passe"],
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
        # Toujours retourner 200 — anti-énumération
        return success_response(
            message="Si un compte existe avec cet email, un lien de réinitialisation a été envoyé."
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Confirmer la réinitialisation de mot de passe",
        description=(
            "Valide le token reçu par email et définit le nouveau mot de passe.\n"
            "Le token est invalidé après usage."
        ),
        request=PasswordResetConfirmSerializer,
        responses={
            200: OpenApiResponse(description="Mot de passe réinitialisé — l'utilisateur peut se connecter"),
            400: OpenApiResponse(description="Token invalide, expiré ou mots de passe non concordants"),
        },
        tags=["Mot de passe"],
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return success_response(
                data={'login': user.login},
                message="Mot de passe réinitialisé avec succès. Vous pouvez maintenant vous connecter."
            )
        return error_response(errors=serializer.errors, message="Données invalides.")