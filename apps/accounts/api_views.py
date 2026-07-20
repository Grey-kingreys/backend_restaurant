# apps/accounts/api_views.py
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.shortcuts import get_object_or_404
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import User, Permission, RoleConfig
from .permissions import (
    IsRestaurantActive, IsSameRestaurant,
    HasManageEquipe, HasImpersonate, HasManageRoles,
)
from .perm_codes import PERM_MANAGE_ROLES, PERM_DEACTIVATE_EQUIPE
from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    UserMeSerializer,
    UpdateMeSerializer,
    UserListSerializer,
    UserDetailSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    AdminPasswordResetSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    ChangePasswordSerializer,
    PermissionSerializer,
    RoleConfigListSerializer,
    RoleConfigDetailSerializer,
    RoleConfigCreateSerializer,
    RoleConfigUpdateSerializer,
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

    @extend_schema(
        summary="Modifier son profil",
        description="Permet à l'utilisateur connecté de modifier son nom, son email et son téléphone.",
        request=UpdateMeSerializer,
        responses={
            200: UserMeSerializer,
            400: OpenApiResponse(description="Données invalides"),
        },
        tags=["Auth"],
    )
    def patch(self, request):
        serializer = UpdateMeSerializer(
            request.user, data=request.data, partial=True, context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return success_response(
                data=UserMeSerializer(request.user).data,
                message="Profil mis à jour avec succès.",
            )
        return error_response(errors=serializer.errors)


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
        return error_response(errors=serializer.errors, message="Impossible de changer le mot de passe.")


# ─────────────────────────────────────────────────────────────────────────────
# CRUD UTILISATEURS
# ─────────────────────────────────────────────────────────────────────────────

class UserListCreateView(APIView):
    permission_classes = [IsAuthenticated, HasManageEquipe, IsRestaurantActive]

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

        # Par défaut : afficher uniquement les utilisateurs actifs
        # Ajouter ?actif=false pour voir les inactifs
        actif = request.query_params.get('actif', 'true')
        qs = qs.filter(actif=actif.lower() == 'true')

        # Filtres optionnels
        role = request.query_params.get('role')
        if role:
            qs = qs.filter(role=role)

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
    permission_classes = [IsAuthenticated, HasManageEquipe, IsRestaurantActive]

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
        # Réservée à la permission deactivate_equipe (Admin, ou rôle custom l'ayant)
        if not request.user.has_permission(PERM_DEACTIVATE_EQUIPE):
            return error_response(
                message="Vous n'avez pas la permission de désactiver un membre.",
                status_code=status.HTTP_403_FORBIDDEN
            )
        user = self.get_object(pk, request)
        if user == request.user:
            return error_response(
                message="Vous ne pouvez pas désactiver votre propre compte."
            )
        if not user.actif:
            return error_response(
                message=f"Cet utilisateur est déjà désactivé."
            )
        login = user.login
        # Soft delete : marquer comme inactif au lieu de supprimer
        user.actif = False
        user.save(update_fields=['actif'])
        return success_response(message=f"Utilisateur '{login}' désactivé. Ses données historiques sont conservées.")


class UserToggleView(APIView):
    permission_classes = [IsAuthenticated, HasManageEquipe, IsRestaurantActive]

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
        if not request.user.has_permission(PERM_DEACTIVATE_EQUIPE):
            return error_response(
                message="Vous n'avez pas la permission d'activer/désactiver un membre.",
                status_code=status.HTTP_403_FORBIDDEN
            )
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
    permission_classes = [IsAuthenticated, HasManageEquipe, IsRestaurantActive]

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


class ImpersonateView(APIView):
    permission_classes = [IsAuthenticated, HasImpersonate, IsRestaurantActive]

    @extend_schema(
        summary="Simuler un utilisateur du restaurant",
        description=(
            "Génère des tokens JWT pour un utilisateur du restaurant.\n"
            "Réservé à l'Administrateur uniquement.\n\n"
            "Restrictions :\n"
            "- Impossible de simuler un Admin ou Super Admin\n"
            "- Impossible de simuler un utilisateur inactif\n"
            "- Impossible de se simuler soi-même"
        ),
        request=None,
        responses={
            200: OpenApiResponse(description="Tokens JWT de l'utilisateur simulé"),
            400: OpenApiResponse(description="Simulation impossible"),
            403: OpenApiResponse(description="Accès réservé à l'Administrateur"),
            404: OpenApiResponse(description="Utilisateur introuvable"),
        },
        tags=["Auth"],
    )
    def post(self, request, pk):
        target = get_object_or_404(
            User, pk=pk, restaurant=request.user.restaurant
        )

        if target == request.user:
            return error_response(message="Vous ne pouvez pas vous simuler vous-même.")

        if target.role in ('Rsuper_admin', 'Radmin'):
            return error_response(message="Impossible de simuler un Administrateur.")

        if not target.actif:
            return error_response(message="Impossible de simuler un utilisateur inactif.")

        refresh = RefreshToken.for_user(target)
        return success_response(
            data={
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserMeSerializer(target).data,
            },
            message=f"Simulation de {target.nom_complet or target.login} ({target.get_role_display()})"
        )


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


# ─────────────────────────────────────────────────────────────────────────────
# PERMISSIONS CATALOGUE
# ─────────────────────────────────────────────────────────────────────────────

class PermissionListView(APIView):
    """GET /api/accounts/permissions/ — Liste de toutes les permissions disponibles."""
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    @extend_schema(
        summary="Catalogue des permissions",
        description="Retourne toutes les permissions disponibles, groupées par catégorie. Accès : manage_roles.",
        responses={200: PermissionSerializer(many=True)},
        tags=["Rôles"],
    )
    def get(self, request):
        if not request.user.has_permission(PERM_MANAGE_ROLES):
            return error_response(
                message="Vous n'avez pas la permission de gérer les rôles.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        perms = Permission.objects.all().order_by('categorie', 'label')
        return success_response(data=PermissionSerializer(perms, many=True).data)


# ─────────────────────────────────────────────────────────────────────────────
# CRUD RÔLES
# ─────────────────────────────────────────────────────────────────────────────

class RoleConfigListCreateView(APIView):
    """
    GET  /api/accounts/roles/ — Rôles système + rôles custom du restaurant
    POST /api/accounts/roles/ — Créer un rôle custom
    """
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    @extend_schema(
        summary="Liste des rôles",
        description=(
            "Retourne les rôles système (is_system=True) + les rôles custom du restaurant connecté.\n"
            "Accès : manage_roles."
        ),
        responses={200: RoleConfigListSerializer(many=True)},
        tags=["Rôles"],
    )
    def get(self, request):
        if not request.user.has_permission(PERM_MANAGE_ROLES):
            return error_response(
                message="Vous n'avez pas la permission de gérer les rôles.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        qs = RoleConfig.objects.filter(
            Q(is_system=True) | Q(restaurant=request.user.restaurant)
        ).prefetch_related('permissions', 'users').order_by('is_system', 'nom')
        return success_response(
            data={
                'count': qs.count(),
                'roles': RoleConfigListSerializer(qs, many=True).data,
            }
        )

    @extend_schema(
        summary="Créer un rôle custom",
        description="Crée un rôle personnalisé pour le restaurant. Accès : manage_roles.",
        request=RoleConfigCreateSerializer,
        responses={
            201: RoleConfigDetailSerializer,
            400: OpenApiResponse(description="Données invalides"),
            403: OpenApiResponse(description="Permission manage_roles requise"),
        },
        tags=["Rôles"],
    )
    def post(self, request):
        if not request.user.has_permission(PERM_MANAGE_ROLES):
            return error_response(
                message="Vous n'avez pas la permission de créer des rôles.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        s = RoleConfigCreateSerializer(data=request.data, context={'request': request})
        if s.is_valid():
            role = s.create(s.validated_data)
            return success_response(
                data=RoleConfigDetailSerializer(role).data,
                message=f"Rôle '{role.nom}' créé avec succès.",
                status_code=status.HTTP_201_CREATED,
            )
        return error_response(errors=s.errors, message="Données invalides.")


class RoleConfigDetailView(APIView):
    """
    GET    /api/accounts/roles/<pk>/ — Détail d'un rôle
    PATCH  /api/accounts/roles/<pk>/ — Modifier un rôle custom
    DELETE /api/accounts/roles/<pk>/ — Supprimer un rôle custom
    """
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    def _get_role(self, pk, request):
        return get_object_or_404(RoleConfig, pk=pk)

    def _check_perm(self, request):
        if not request.user.has_permission(PERM_MANAGE_ROLES):
            return error_response(
                message="Vous n'avez pas la permission de gérer les rôles.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return None

    @extend_schema(
        summary="Détail d'un rôle",
        responses={200: RoleConfigDetailSerializer},
        tags=["Rôles"],
    )
    def get(self, request, pk):
        if e := self._check_perm(request):
            return e
        role = self._get_role(pk, request)
        if not role.is_system and role.restaurant != request.user.restaurant:
            return error_response(message="Rôle introuvable.", status_code=status.HTTP_404_NOT_FOUND)
        return success_response(data=RoleConfigDetailSerializer(role).data)

    @extend_schema(
        summary="Modifier un rôle",
        description="Modification partielle (nom, dashboard_type, permissions) d'un rôle custom du restaurant. Les rôles système sont protégés (403).",
        request=RoleConfigUpdateSerializer,
        responses={
            200: RoleConfigDetailSerializer,
            400: OpenApiResponse(description="Données invalides"),
        },
        tags=["Rôles"],
    )
    def patch(self, request, pk):
        if e := self._check_perm(request):
            return e
        role = self._get_role(pk, request)
        if role.is_system:
            return error_response(
                message="Les rôles système ne sont pas modifiables.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if role.restaurant != request.user.restaurant:
            return error_response(message="Rôle introuvable.", status_code=status.HTTP_404_NOT_FOUND)
        s = RoleConfigUpdateSerializer(role, data=request.data, partial=True)
        if s.is_valid():
            role = s.update(role, s.validated_data)
            return success_response(
                data=RoleConfigDetailSerializer(role).data,
                message=f"Rôle '{role.nom}' mis à jour.",
            )
        return error_response(errors=s.errors, message="Données invalides.")

    @extend_schema(
        summary="Supprimer un rôle",
        description="Suppression d'un rôle. Impossible si des utilisateurs y sont encore associés.",
        responses={
            200: OpenApiResponse(description="Rôle supprimé"),
            400: OpenApiResponse(description="Des utilisateurs utilisent encore ce rôle"),
        },
        tags=["Rôles"],
    )
    def delete(self, request, pk):
        if e := self._check_perm(request):
            return e
        role = self._get_role(pk, request)
        if role.is_system:
            return error_response(
                message="Les rôles système ne peuvent pas être supprimés.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if role.restaurant != request.user.restaurant:
            return error_response(message="Rôle introuvable.", status_code=status.HTTP_404_NOT_FOUND)
        nb_users = role.users.count()
        if nb_users > 0:
            return error_response(
                message=f"Impossible de supprimer ce rôle : {nb_users} utilisateur(s) l'utilisent encore."
            )
        nom = role.nom
        role.delete()
        return success_response(message=f"Rôle '{nom}' supprimé.")