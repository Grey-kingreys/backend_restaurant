# apps/commandes/urls.py
from django.urls import path
from . import api_views

app_name = 'commandes'

urlpatterns = [

    # ── Panier (Table) ────────────────────────────────────────────────────
    path('panier/',             api_views.PanierView.as_view(),        name='panier'),
    path('panier/<int:plat_id>/', api_views.PanierItemView.as_view(),  name='panier-item'),

    # ── Validation panier → commande (Table) ──────────────────────────────
    path('valider/',            api_views.CommandeValiderView.as_view(), name='valider'),

    # ── Mes commandes — Table (session QR courante) ───────────────────────
    path('mes-commandes/',      api_views.MesCommandesView.as_view(),  name='mes-commandes'),

    # ── Toutes les commandes — Serveur, Chef, Admin, Manager ──────────────
    path('',                    api_views.AllCommandesView.as_view(),  name='all-commandes'),

    # ── Détail d'une commande (tous les rôles autorisés) ──────────────────
    path('<int:pk>/',           api_views.CommandeDetailView.as_view(), name='commande-detail'),

    # ── Vue Cuisine — Cuisinier / Chef Cuisinier ──────────────────────────
    path('cuisine/',            api_views.CuisinierCommandesView.as_view(), name='cuisine'),
    path('<int:pk>/prete/',     api_views.CommandePreteView.as_view(),      name='prete'),

    # ── Vue Serveur — transitions SERVIE et PAYÉE ─────────────────────────
    path('<int:pk>/servie/',    api_views.CommandeServieView.as_view(),  name='servie'),
    path('<int:pk>/payee/',     api_views.CommandePayeeView.as_view(),   name='payee'),

    # ── Reçu PDF ──────────────────────────────────────────────────────────
    path('<int:pk>/recu/',      api_views.CommandeRecuView.as_view(),   name='recu'),

    # ── Suppression (Admin uniquement) ────────────────────────────────────
    path('<int:pk>/supprimer/', api_views.CommandeDeleteView.as_view(), name='supprimer'),
]