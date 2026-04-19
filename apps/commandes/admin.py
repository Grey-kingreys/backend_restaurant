# apps/commandes/admin.py
from django.contrib import admin
from .models import Commande, CommandeItem, PanierItem


class CommandeItemInline(admin.TabularInline):
    model  = CommandeItem
    extra  = 0
    readonly_fields = ['prix_unitaire', 'sous_total_display']
    fields = ['plat', 'quantite', 'prix_unitaire', 'sous_total_display']

    def sous_total_display(self, obj):
        return f"{obj.sous_total:,.0f} GNF".replace(',', ' ')
    sous_total_display.short_description = "Sous-total"


@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    list_display    = ['id', 'restaurant', 'table', 'statut', 'montant_total',
                       'serveur_ayant_servi', 'cuisinier_ayant_prepare', 'date_commande']
    list_filter     = ['restaurant', 'statut', 'date_commande']
    search_fields   = ['table__login', 'restaurant__nom']
    readonly_fields = ['date_commande', 'date_modification', 'montant_total']
    ordering        = ['-date_commande']
    inlines         = [CommandeItemInline]
    fieldsets = (
        ('Identification',   {'fields': ('restaurant', 'table', 'session')}),
        ('Statut & Montant', {'fields': ('statut', 'montant_total', 'date_paiement')}),
        ('Traçabilité',      {'fields': ('serveur_ayant_servi', 'cuisinier_ayant_prepare')}),
        ('Dates',            {'fields': ('date_commande', 'date_modification'), 'classes': ('collapse',)}),
    )


@admin.register(PanierItem)
class PanierItemAdmin(admin.ModelAdmin):
    list_display  = ['table', 'plat', 'quantite', 'sous_total_display', 'date_ajout']
    list_filter   = ['date_ajout']
    search_fields = ['table__login', 'plat__nom']
    readonly_fields = ['date_ajout']

    def sous_total_display(self, obj):
        return f"{obj.sous_total:,.0f} GNF".replace(',', ' ')
    sous_total_display.short_description = "Sous-total"