# apps/accounts/permissions.py
from rest_framework.permissions import BasePermission


class IsSuperAdmin(BasePermission):
    message = "Accès réservé au Super Administrateur."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Rsuper_admin'
        )


class IsAdmin(BasePermission):
    message = "Accès réservé à l'Administrateur."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Radmin'
        )


class IsManager(BasePermission):
    message = "Accès réservé au Manager."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Rmanager'
        )


class IsAdminOrManager(BasePermission):
    message = "Accès réservé à l'Administrateur ou au Manager."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in ('Radmin', 'Rmanager')
        )


class IsServeur(BasePermission):
    message = "Accès réservé au Serveur."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Rserveur'
        )


class IsChefCuisinier(BasePermission):
    message = "Accès réservé au Chef Cuisinier."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Rchef_cuisinier'
        )


class IsCuisinier(BasePermission):
    message = "Accès réservé au Cuisinier."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Rcuisinier'
        )


class IsCuisinierAny(BasePermission):
    message = "Accès réservé au Chef Cuisinier ou au Cuisinier."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in ('Rchef_cuisinier', 'Rcuisinier')
        )


class IsComptable(BasePermission):
    message = "Accès réservé au Comptable."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Rcomptable'
        )


class IsTable(BasePermission):
    message = "Accès réservé aux comptes Table."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Rtable'
        )


class IsRestaurantActive(BasePermission):
    """
    Vérifie que le restaurant de l'utilisateur est actif.
    À combiner avec d'autres permissions.
    """
    message = "Votre restaurant est suspendu. Contactez le support."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == 'Rsuper_admin':
            return True
        return (
            request.user.restaurant is not None
            and request.user.restaurant.is_active
        )


class IsSameRestaurant(BasePermission):
    """
    Vérifie que l'objet cible appartient au même restaurant que le user connecté.
    À utiliser dans has_object_permission.
    """
    message = "Vous n'avez pas accès à cet utilisateur."

    def has_object_permission(self, request, view, obj):
        if request.user.is_super_admin():
            return True
        return obj.restaurant == request.user.restaurant