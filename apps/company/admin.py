# apps/company/admin.py
from django.contrib import admin
from .models import Restaurant, OnboardingToken


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ['nom', 'email_admin', 'telephone', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['nom', 'email_admin', 'telephone']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['suspendre_restaurants', 'reactiver_restaurants']

    def suspendre_restaurants(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"{queryset.count()} restaurant(s) suspendu(s).")
    suspendre_restaurants.short_description = "Suspendre les restaurants selectionnes"

    def reactiver_restaurants(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, f"{queryset.count()} restaurant(s) reactive(s).")
    reactiver_restaurants.short_description = "Reactiver les restaurants selectionnes"


@admin.register(OnboardingToken)
class OnboardingTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'get_restaurant', 'is_used', 'expires_at', 'created_at']
    list_filter = ['is_used']
    search_fields = ['user__login', 'user__email']
    readonly_fields = ['token', 'created_at', 'expires_at']

    def get_restaurant(self, obj):
        return obj.user.restaurant
    get_restaurant.short_description = "Restaurant"

    def has_change_permission(self, request, obj=None):
        # Les tokens sont immuables — lecture seule dans l'admin
        return False