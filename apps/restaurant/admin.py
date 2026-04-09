# apps/restaurant/admin.py
from django.contrib import admin
from .models import TableRestaurant, TableToken, TableSession


@admin.register(TableRestaurant)
class TableRestaurantAdmin(admin.ModelAdmin):
    list_display = [
        'numero_table', 'restaurant', 'nombre_places',
        'utilisateur', 'get_statut', 'date_creation'
    ]
    list_filter = ['restaurant']
    search_fields = ['numero_table', 'restaurant__nom', 'utilisateur__login']
    readonly_fields = ['date_creation', 'date_modification']
    ordering = ['restaurant', 'numero_table']

    def get_statut(self, obj):
        return obj.get_statut_actuel()
    get_statut.short_description = "Statut actuel"


@admin.register(TableToken)
class TableTokenAdmin(admin.ModelAdmin):
    list_display = ['table', 'get_restaurant', 'est_valide', 'date_creation', 'date_derniere_utilisation']
    list_filter = ['table__restaurant']
    search_fields = ['table__login', 'table__restaurant__nom']
    readonly_fields = ['date_creation', 'date_derniere_utilisation', 'token', 'password_hash']

    def get_restaurant(self, obj):
        return obj.table.restaurant
    get_restaurant.short_description = "Restaurant"

    def est_valide(self, obj):
        return obj.est_valide()
    est_valide.boolean = True
    est_valide.short_description = "Token valide"


@admin.register(TableSession)
class TableSessionAdmin(admin.ModelAdmin):
    list_display = [
        'table', 'get_restaurant', 'est_active',
        'date_creation', 'date_paiement', 'commande_payee'
    ]
    list_filter = ['est_active', 'table__restaurant']
    search_fields = ['table__login', 'table__restaurant__nom']
    readonly_fields = ['session_token', 'django_session_key', 'date_creation', 'date_derniere_activite']

    def get_restaurant(self, obj):
        return obj.table.restaurant
    get_restaurant.short_description = "Restaurant"