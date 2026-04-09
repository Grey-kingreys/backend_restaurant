# apps/accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        'login', 'nom_complet', 'role', 'restaurant',
        'actif', 'must_change_password', 'date_creation'
    ]
    list_filter = ['role', 'actif', 'must_change_password', 'restaurant']
    search_fields = ['login', 'nom_complet', 'email', 'telephone']
    ordering = ['restaurant', 'role', 'login']
    readonly_fields = ['date_creation']

    fieldsets = (
        ('Identifiants', {
            'fields': ('login', 'password')
        }),
        ('Informations personnelles', {
            'fields': ('nom_complet', 'email', 'telephone')
        }),
        ('Role & Restaurant', {
            'fields': ('role', 'restaurant', 'actif', 'must_change_password')
        }),
        ('Permissions Django', {
            'fields': ('is_staff', 'is_active', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',)
        }),
        ('Dates', {
            'fields': ('date_creation', 'last_login'),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = (
        ('Nouveau utilisateur', {
            'classes': ('wide',),
            'fields': (
                'login', 'password1', 'password2',
                'role', 'restaurant',
                'nom_complet', 'email', 'telephone',
                'actif', 'must_change_password'
            ),
        }),
    )

    # Le champ USERNAME_FIELD est 'login' pas 'username'
    # On override pour eviter l'erreur Django admin
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        return form