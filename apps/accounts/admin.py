# apps/accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, PasswordResetToken


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        'login', 'nom_complet', 'email', 'role', 'restaurant',
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
        ('Rôle & Restaurant', {
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
        ('Nouvel utilisateur', {
            'classes': ('wide',),
            'fields': (
                'login', 'password1', 'password2',
                'role', 'restaurant',
                'nom_complet', 'email', 'telephone',
                'actif', 'must_change_password'
            ),
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        return form


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_used', 'expires_at', 'created_at']
    list_filter = ['is_used']
    search_fields = ['user__login', 'user__email']
    readonly_fields = ['token', 'created_at', 'expires_at']

    def has_change_permission(self, request, obj=None):
        return False