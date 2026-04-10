# apps/company/permissions.py
from rest_framework.permissions import BasePermission


class IsSuperAdmin(BasePermission):
    """
    Acces reserve exclusivement au Super Admin (Rsuper_admin).
    Utilise pour la gestion de la plateforme SaaS (CRUD restaurants).
    """
    message = "Acces reserve au Super Administrateur."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'Rsuper_admin'
        )


class IsRestaurantActive(BasePermission):
    """
    Verifie que le restaurant de l'utilisateur est actif (non suspendu).
    A combiner avec d'autres permissions.
    """
    message = "Votre restaurant est suspendu. Contactez le support."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Le Super Admin n'appartient a aucun restaurant
        if request.user.role == 'Rsuper_admin':
            return True
        return (
            request.user.restaurant is not None
            and request.user.restaurant.is_active
        )