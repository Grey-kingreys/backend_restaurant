# apps/restaurant/api_urls.py
"""
URLs DRF pour l'app restaurant — Phase 6.

Préfixe : /api/v1/restaurant/

Note : L'endpoint de connexion QR (/api/v1/auth/qr/<token>/)
est enregistré dans apps/accounts/api_urls.py pour cohérence
avec les autres endpoints d'authentification.
"""
from django.urls import path
from . import api_views

app_name = 'restaurant_api'

urlpatterns = [

    # ── CRUD Tables ───────────────────────────────────────────────────────
    path(
        'tables/',
        api_views.TableListView.as_view(),
        name='table-list'
    ),
    path(
        'tables/<int:pk>/',
        api_views.TableDetailView.as_view(),
        name='table-detail'
    ),

    # ── QR Code ───────────────────────────────────────────────────────────
    path(
        'tables/<int:pk>/qr/',
        api_views.QRCodeInfoView.as_view(),
        name='qr-info'
    ),
    path(
        'tables/<int:pk>/qr/generer/',
        api_views.QRCodeGenererView.as_view(),
        name='qr-generer'
    ),

    # ── Sessions ──────────────────────────────────────────────────────────
    path(
        'sessions/',
        api_views.TableSessionListView.as_view(),
        name='sessions'
    ),

    # ── Dashboard Serveur ─────────────────────────────────────────────────
    path(
        'dashboard/serveur/',
        api_views.ServeurDashboardView.as_view(),
        name='dashboard-serveur'
    ),

    # ── Actions Serveur sur les commandes ─────────────────────────────────
    path(
        'commandes/<int:pk>/servie/',
        api_views.ServeurCommandeServieView.as_view(),
        name='commande-servie'
    ),
    path(
        'commandes/<int:pk>/payee/',
        api_views.ServeurCommandePayeeView.as_view(),
        name='commande-payee'
    ),
]