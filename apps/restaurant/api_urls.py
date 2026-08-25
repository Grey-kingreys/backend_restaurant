# apps/restaurant/api_urls.py
"""
URLs DRF pour l'app restaurant - Phase 6.

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

    # ── Vérification position GPS (Rtable) ───────────────────────────────
    path(
        'tables/check-position/',
        api_views.CheckPositionView.as_view(),
        name='check-position'
    ),
    path(
        'tables/check-distance/',
        api_views.CheckDistanceView.as_view(),
        name='check-distance'
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

    # ── Réservations (gestion staff) ──────────────────────────────────────
    path(
        'reservations/',
        api_views.ReservationListView.as_view(),
        name='reservations'
    ),
    path(
        'reservations/<int:pk>/confirmer/',
        api_views.ReservationConfirmerView.as_view(),
        name='reservation-confirmer'
    ),
    path(
        'reservations/<int:pk>/refuser/',
        api_views.ReservationRefuserView.as_view(),
        name='reservation-refuser'
    ),
    path(
        'reservations/<int:pk>/reaffecter/',
        api_views.ReservationReaffecterView.as_view(),
        name='reservation-reaffecter'
    ),
    path(
        'reservations/<int:pk>/terminer/',
        api_views.ReservationTerminerView.as_view(),
        name='reservation-terminer'
    ),
    path(
        'reservations/<int:pk>/no-show/',
        api_views.ReservationNoShowView.as_view(),
        name='reservation-no-show'
    ),
    path(
        'reservations/<int:pk>/bloquer-client/',
        api_views.ReservationBloquerClientView.as_view(),
        name='reservation-bloquer-client'
    ),
    path(
        'reservations/<int:pk>/debloquer-client/',
        api_views.ReservationDebloquerClientView.as_view(),
        name='reservation-debloquer-client'
    ),
]