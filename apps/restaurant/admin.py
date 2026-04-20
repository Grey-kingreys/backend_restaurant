# apps/restaurant/admin.py
# Phase 6 — mis à jour pour la structure SaaS v2
from django.contrib import admin
from .models import TableRestaurant, TableToken, TableSession


@admin.register(TableRestaurant)
class TableRestaurantAdmin(admin.ModelAdmin):
    list_display    = ['numero_table', 'nombre_places', 'utilisateur_login', 'restaurant', 'date_creation']
    list_filter     = ['utilisateur__restaurant', 'nombre_places']
    search_fields   = ['numero_table', 'utilisateur__login']
    readonly_fields = ['date_creation', 'date_modification']

    def utilisateur_login(self, obj):
        return obj.utilisateur.login
    utilisateur_login.short_description = "Compte Table"

    def restaurant(self, obj):
        return obj.utilisateur.restaurant.nom if obj.utilisateur.restaurant else '—'
    restaurant.short_description = "Restaurant"

    fieldsets = (
        ('Table physique', {'fields': ('numero_table', 'nombre_places')}),
        ('Compte associé', {'fields': ('utilisateur',)}),
        ('Dates',          {'fields': ('date_creation', 'date_modification'), 'classes': ('collapse',)}),
    )


@admin.register(TableToken)
class TableTokenAdmin(admin.ModelAdmin):
    list_display    = ['table', 'est_valide_display', 'date_creation', 'date_derniere_utilisation']
    list_filter     = ['date_creation']
    search_fields   = ['table__login']
    readonly_fields = ['token', 'password_hash', 'date_creation', 'date_derniere_utilisation']

    def est_valide_display(self, obj):
        return "✅ Valide" if obj.est_valide() else "❌ Invalide"
    est_valide_display.short_description = "Validité"


@admin.register(TableSession)
class TableSessionAdmin(admin.ModelAdmin):
    list_display    = ['table', 'est_active', 'date_creation', 'date_paiement', 'temps_restant']
    list_filter     = ['est_active', 'date_creation']
    search_fields   = ['table__login', 'session_token']
    readonly_fields = ['session_token', 'django_session_key', 'date_creation', 'date_derniere_activite']

    def temps_restant(self, obj):
        if not obj.date_paiement or not obj.est_active:
            return "—"
        from django.utils import timezone
        elapsed  = timezone.now() - obj.date_paiement
        restant  = 60 - int(elapsed.total_seconds())
        if restant <= 0:
            return "⏱️ Devrait expirer"
        return f"⏱️ {restant}s"
    temps_restant.short_description = "Temps restant"