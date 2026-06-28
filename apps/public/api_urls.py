# apps/public/api_urls.py
# Endpoints publics (AllowAny) pour la vitrine client.
# Préfixe : /api/public/

from django.urls import path
from . import api_views

app_name = 'public_api'

urlpatterns = [

    # ── Authentification client ───────────────────────────────────────────
    path(
        'auth/register/',
        api_views.ClientRegisterView.as_view(),
        name='client-register'
    ),

    # ── Restaurants publics ───────────────────────────────────────────────
    path(
        'restaurants/',
        api_views.RestaurantListPublicView.as_view(),
        name='restaurant-list'
    ),
    path(
        'plats/',
        api_views.PlatsPublicListView.as_view(),
        name='plats-list'
    ),
    path(
        'restaurants/<slug:slug>/',
        api_views.RestaurantDetailPublicView.as_view(),
        name='restaurant-detail'
    ),

    # ── Commander (Rclient authentifié) ──────────────────────────────────
    path(
        'restaurants/<slug:slug>/commander/',
        api_views.CommanderView.as_view(),
        name='commander'
    ),

    # ── Réservation de table ──────────────────────────────────────────────
    path(
        'restaurants/<slug:slug>/tables/',
        api_views.TablesDisponiblesView.as_view(),
        name='tables-disponibles'
    ),
    path(
        'restaurants/<slug:slug>/reserver/',
        api_views.ReserverView.as_view(),
        name='reserver'
    ),
    path(
        'mes-reservations/',
        api_views.MesReservationsView.as_view(),
        name='mes-reservations'
    ),
    path(
        'reservations/<int:pk>/annuler/',
        api_views.AnnulerReservationView.as_view(),
        name='annuler-reservation'
    ),

    # ── Mes commandes (Rclient authentifié) ──────────────────────────────
    path(
        'mes-commandes/',
        api_views.MesCommandesClientView.as_view(),
        name='mes-commandes'
    ),

    # ── Suivi commande (clé publique) ─────────────────────────────────────
    path(
        'commandes/<str:cle_suivi>/',
        api_views.SuiviCommandeView.as_view(),
        name='suivi-commande'
    ),
]
