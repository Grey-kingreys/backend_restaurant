# apps/company/urls.py
from django.urls import path
from . import api_views

app_name = 'company'

urlpatterns = [
    # ── Restaurants CRUD ──────────────────────────────────────────────────
    path(
        'restaurants/',
        api_views.RestaurantListCreateView.as_view(),
        name='restaurant-list-create'
    ),
    path(
        'restaurants/<int:pk>/',
        api_views.RestaurantDetailView.as_view(),
        name='restaurant-detail'
    ),
    path(
        'restaurants/<int:pk>/suspend/',
        api_views.RestaurantSuspendView.as_view(),
        name='restaurant-suspend'
    ),
    path(
        'restaurants/<int:pk>/activate/',
        api_views.RestaurantActivateView.as_view(),
        name='restaurant-activate'
    ),

    # ── Onboarding premiere connexion Admin ───────────────────────────────
    path(
        'onboarding/<uuid:token>/',
        api_views.OnboardingValidateView.as_view(),
        name='onboarding-validate'
    ),

    # ── Stats globales plateforme ─────────────────────────────────────────
    path(
        'stats/',
        api_views.PlatformStatsView.as_view(),
        name='platform-stats'
    ),
]