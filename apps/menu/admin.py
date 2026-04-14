# apps/menu/admin.py
from django.contrib import admin
from .models import Plat


@admin.register(Plat)
class PlatAdmin(admin.ModelAdmin):
    list_display = [
        'nom', 'restaurant', 'categorie', 'prix_formate_admin',
        'disponible', 'necessite_validation_cuisine', 'date_modification'
    ]
    list_filter = [
        'restaurant', 'categorie', 'disponible', 'necessite_validation_cuisine'
    ]
    search_fields = ['nom', 'description', 'restaurant__nom']
    readonly_fields = ['date_creation', 'date_modification', 'image_preview']
    list_editable = ['disponible']
    ordering = ['restaurant', 'categorie', 'nom']
    actions = ['activer_plats', 'desactiver_plats']

    fieldsets = (
        ('Restaurant (SaaS)', {
            'fields': ('restaurant',),
        }),
        ('Informations', {
            'fields': ('nom', 'description', 'image', 'image_preview')
        }),
        ('Prix & Catégorie', {
            'fields': ('prix_unitaire', 'categorie')
        }),
        ('Disponibilité', {
            'fields': ('disponible', 'necessite_validation_cuisine')
        }),
        ('Dates', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )

    def prix_formate_admin(self, obj):
        return f"{obj.prix_unitaire:,.0f} GNF".replace(',', ' ')
    prix_formate_admin.short_description = "Prix"

    def image_preview(self, obj):
        if obj.image:
            from django.utils.html import format_html
            return format_html(
                '<img src="{}" style="max-height:120px;max-width:120px;'
                'border-radius:6px;object-fit:cover;" />',
                obj.image.url
            )
        return "—"
    image_preview.short_description = "Aperçu"

    def activer_plats(self, request, queryset):
        updated = queryset.update(disponible=True)
        self.message_user(request, f"{updated} plat(s) activé(s).")
    activer_plats.short_description = "✅ Activer les plats sélectionnés"

    def desactiver_plats(self, request, queryset):
        updated = queryset.update(disponible=False)
        self.message_user(request, f"{updated} plat(s) désactivé(s).")
    desactiver_plats.short_description = "❌ Désactiver les plats sélectionnés"