# apps/menu/admin.py
from django.contrib import admin
from .models import Plat


@admin.register(Plat)
class PlatAdmin(admin.ModelAdmin):
    list_display = [
        'nom', 'restaurant', 'categorie', 'prix_unitaire',
        'disponible', 'necessite_validation_cuisine', 'date_modification'
    ]
    list_filter = ['restaurant', 'categorie', 'disponible', 'necessite_validation_cuisine']
    search_fields = ['nom', 'description', 'restaurant__nom']
    readonly_fields = ['date_creation', 'date_modification']
    list_editable = ['disponible']
    ordering = ['restaurant', 'categorie', 'nom']
    actions = ['activer_plats', 'desactiver_plats']

    fieldsets = (
        ('Informations', {
            'fields': ('restaurant', 'nom', 'description', 'image')
        }),
        ('Prix & Categorie', {
            'fields': ('prix_unitaire', 'categorie')
        }),
        ('Disponibilite', {
            'fields': ('disponible', 'necessite_validation_cuisine')
        }),
        ('Dates', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )

    def activer_plats(self, request, queryset):
        queryset.update(disponible=True)
        self.message_user(request, f"{queryset.count()} plat(s) active(s).")
    activer_plats.short_description = "Activer les plats selectionnes"

    def desactiver_plats(self, request, queryset):
        queryset.update(disponible=False)
        self.message_user(request, f"{queryset.count()} plat(s) desactive(s).")
    desactiver_plats.short_description = "Desactiver les plats selectionnes"