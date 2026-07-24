# apps/accounts/permissions.py
from rest_framework.permissions import BasePermission
from .perm_codes import (
    PERM_MANAGE_EQUIPE, PERM_IMPERSONATE, PERM_MANAGE_ROLES,
    PERM_MANAGE_MENU,
    PERM_VIEW_COMMANDES, PERM_MANAGE_COMMANDES,
    PERM_VIEW_CUISINE, PERM_MANAGE_CUISINE,
    PERM_MANAGE_TABLES, PERM_VIEW_TABLES,
    PERM_MANAGE_CAISSE_COMPTABLE, PERM_VIEW_CAISSE_GLOBALE,
    PERM_MANAGE_CAISSE_GLOBALE, PERM_VIEW_CAISSE_GENERALE,
    PERM_VIEW_REMISES, PERM_MANAGE_REMISES,
    PERM_MANAGE_RESTAURANT,
)


# ─────────────────────────────────────────────────────────────────────────────
# Permissions structurelles (rôles hardcodés — ne migrent pas vers RoleConfig)
# ─────────────────────────────────────────────────────────────────────────────

class IsSuperAdmin(BasePermission):
    message = "Accès réservé au Super Administrateur."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Rsuper_admin'
        )


class IsTable(BasePermission):
    message = "Accès réservé aux comptes Table."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Rtable'
        )


class IsClient(BasePermission):
    message = "Accès réservé aux comptes Client."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Rclient'
        )


class IsRestaurantActive(BasePermission):
    """Vérifie que le restaurant de l'utilisateur est actif."""
    message = "Votre restaurant est suspendu. Contactez le support."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Super Admin et Client ne sont pas liés à un restaurant
        if request.user.role in ('Rsuper_admin', 'Rclient'):
            return True
        return (
            request.user.restaurant is not None
            and request.user.restaurant.is_active
        )


class IsSameRestaurant(BasePermission):
    """Vérifie que l'objet cible appartient au même restaurant."""
    message = "Vous n'avez pas accès à cette ressource."

    def has_object_permission(self, request, view, obj):
        if request.user.is_super_admin():
            return True
        return obj.restaurant == request.user.restaurant


# ─────────────────────────────────────────────────────────────────────────────
# Permission générique basée sur has_permission(code)
# ─────────────────────────────────────────────────────────────────────────────

def make_permission(perm_code: str, message: str):
    """Factory : génère une classe DRF Permission pour un code donné."""
    class _Perm(BasePermission):
        pass
    _Perm.message = message
    _Perm.perm_code = perm_code

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.has_permission(self.perm_code)
        )

    _Perm.has_permission = has_permission
    _Perm.__name__ = f'Has_{perm_code}'
    return _Perm


# ─────────────────────────────────────────────────────────────────────────────
# Classes nommées (pour usage dans permission_classes = [...])
# ─────────────────────────────────────────────────────────────────────────────

HasManageEquipe          = make_permission(PERM_MANAGE_EQUIPE,          "Vous n'avez pas la permission de gérer l'équipe.")
HasImpersonate           = make_permission(PERM_IMPERSONATE,            "Vous n'avez pas la permission de simuler un membre.")
HasManageRoles           = make_permission(PERM_MANAGE_ROLES,           "Vous n'avez pas la permission de gérer les rôles.")
HasManageMenu            = make_permission(PERM_MANAGE_MENU,            "Vous n'avez pas la permission de gérer le menu.")
HasViewCommandes         = make_permission(PERM_VIEW_COMMANDES,         "Vous n'avez pas accès aux commandes.")
HasManageCommandes       = make_permission(PERM_MANAGE_COMMANDES,       "Vous n'avez pas la permission de gérer les commandes.")
HasViewCuisine           = make_permission(PERM_VIEW_CUISINE,           "Vous n'avez pas accès à la file cuisine.")
HasManageCuisine         = make_permission(PERM_MANAGE_CUISINE,         "Vous n'avez pas la permission de gérer la cuisine.")
HasManageTables          = make_permission(PERM_MANAGE_TABLES,          "Vous n'avez pas la permission de gérer les tables.")
HasViewTables            = make_permission(PERM_VIEW_TABLES,            "Vous n'avez pas accès aux tables.")
HasManageCaisseComptable = make_permission(PERM_MANAGE_CAISSE_COMPTABLE,"Vous n'avez pas accès à la caisse du jour.")
HasViewCaisseGlobale     = make_permission(PERM_VIEW_CAISSE_GLOBALE,    "Vous n'avez pas accès à la caisse globale.")
HasManageCaisseGlobale   = make_permission(PERM_MANAGE_CAISSE_GLOBALE,  "Vous n'avez pas la permission de gérer la caisse globale.")
HasViewCaisseGenerale    = make_permission(PERM_VIEW_CAISSE_GENERALE,   "Vous n'avez pas accès à la caisse générale.")
HasViewRemises           = make_permission(PERM_VIEW_REMISES,           "Vous n'avez pas accès aux remises.")
HasManageRemises         = make_permission(PERM_MANAGE_REMISES,         "Vous n'avez pas la permission de valider les remises.")
HasManageRestaurant      = make_permission(PERM_MANAGE_RESTAURANT,      "Vous n'avez pas la permission de modifier le restaurant.")


# ─────────────────────────────────────────────────────────────────────────────
# Aliases rétrocompatibles (utilisés dans les vues existantes)
# Ces alias vont disparaître au fur et à mesure du refactoring des vues.
# ─────────────────────────────────────────────────────────────────────────────

class IsAdmin(BasePermission):
    """Alias rétrocompat — préférer HasManageEquipe selon le contexte."""
    message = "Accès réservé à l'Administrateur."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Radmin'
        )


class IsManager(BasePermission):
    message = "Accès réservé au Manager."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Rmanager'
        )


class IsAdminOrManager(BasePermission):
    message = "Accès réservé à l'Administrateur ou au Manager."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ('Radmin', 'Rmanager')
        )


class IsServeur(BasePermission):
    message = "Accès réservé au Serveur."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Rserveur'
        )


class IsChefCuisinier(BasePermission):
    message = "Accès réservé au Chef Cuisinier."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Rchef_cuisinier'
        )


class IsCuisinier(BasePermission):
    message = "Accès réservé au Cuisinier."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Rcuisinier'
        )


class IsCuisinierAny(BasePermission):
    message = "Accès réservé au Chef Cuisinier ou au Cuisinier."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ('Rchef_cuisinier', 'Rcuisinier')
        )


class IsComptable(BasePermission):
    message = "Accès réservé au Comptable."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Rcomptable'
        )
