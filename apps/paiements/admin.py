# apps/paiements/admin.py
from django.contrib import admin
from .models import (
    CaisseGenerale, CaisseGlobale, CaisseComptable,
    MouvementCaisse, RemiseServeur, Paiement, Depense
)


@admin.register(CaisseGenerale)
class CaisseGeneraleAdmin(admin.ModelAdmin):
    list_display = ['restaurant', 'solde', 'solde_initial', 'updated_at']
    readonly_fields = ['created_at', 'updated_at']
    search_fields = ['restaurant__nom']

    def has_delete_permission(self, request, obj=None):
        # La Caisse Generale ne peut jamais etre supprimee
        return False


@admin.register(CaisseGlobale)
class CaisseGlobaleAdmin(admin.ModelAdmin):
    list_display = [
        'restaurant', 'date_ouverture', 'solde',
        'is_closed', 'fermee_par', 'closed_at'
    ]
    list_filter = ['restaurant', 'is_closed', 'date_ouverture']
    search_fields = ['restaurant__nom']
    readonly_fields = ['created_at', 'updated_at', 'closed_at']

    def has_delete_permission(self, request, obj=None):
        # Une caisse fermee est immuable
        if obj and obj.is_closed:
            return False
        return super().has_delete_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if obj and obj.is_closed:
            return False
        return super().has_change_permission(request, obj)


class MouvementCaisseInline(admin.TabularInline):
    model = MouvementCaisse
    extra = 0
    readonly_fields = ['type_mouvement', 'montant', 'motif', 'effectue_par', 'created_at']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CaisseComptable)
class CaisseComptableAdmin(admin.ModelAdmin):
    list_display = [
        'comptable', 'restaurant', 'solde',
        'is_closed', 'opened_at', 'closed_at'
    ]
    list_filter = ['restaurant', 'is_closed']
    search_fields = ['comptable__nom_complet', 'restaurant__nom']
    readonly_fields = ['opened_at', 'closed_at']
    inlines = [MouvementCaisseInline]

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_closed:
            return False
        return super().has_delete_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if obj and obj.is_closed:
            return False
        return super().has_change_permission(request, obj)


@admin.register(MouvementCaisse)
class MouvementCaisseAdmin(admin.ModelAdmin):
    list_display = [
        'caisse_comptable', 'type_mouvement', 'montant',
        'motif', 'effectue_par', 'created_at'
    ]
    list_filter = ['type_mouvement', 'caisse_comptable__restaurant']
    search_fields = ['motif', 'effectue_par__nom_complet']
    readonly_fields = ['created_at']

    def has_change_permission(self, request, obj=None):
        # Les mouvements sont immuables
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RemiseServeur)
class RemiseServeurAdmin(admin.ModelAdmin):
    list_display = [
        'serveur', 'caisse_globale', 'montant_virtuel',
        'montant_physique', 'ecart', 'valide', 'validee_par', 'created_at'
    ]
    list_filter = ['valide', 'caisse_globale__restaurant']
    search_fields = ['serveur__nom_complet', 'caisse_globale__restaurant__nom']
    readonly_fields = ['created_at', 'updated_at', 'ecart']

    def ecart(self, obj):
        e = obj.ecart
        return f"{e} GNF" if e is not None else "—"
    ecart.short_description = "Ecart"


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ['id', 'get_restaurant', 'commande', 'montant', 'date_paiement']
    list_filter = ['commande__restaurant', 'date_paiement']
    search_fields = ['commande__table__login', 'commande__restaurant__nom']
    readonly_fields = ['date_paiement']

    def get_restaurant(self, obj):
        return obj.commande.restaurant
    get_restaurant.short_description = "Restaurant"

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Depense)
class DepenseAdmin(admin.ModelAdmin):
    list_display = [
        'motif', 'get_restaurant', 'caisse_comptable',
        'montant', 'date_depense', 'enregistree_par', 'date_enregistrement'
    ]
    list_filter = ['caisse_comptable__restaurant', 'date_depense']
    search_fields = ['motif', 'enregistree_par__nom_complet']
    readonly_fields = ['date_enregistrement']

    def get_restaurant(self, obj):
        return obj.caisse_comptable.restaurant
    get_restaurant.short_description = "Restaurant"

    def has_change_permission(self, request, obj=None):
        # Une depense enregistree est immuable
        return False