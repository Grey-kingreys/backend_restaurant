# apps/paiements/urls.py
from django.urls import path
from . import api_views

app_name = 'paiements'

urlpatterns = [

    # ── Caisse Generale ───────────────────────────────────────────────────
    path(
        'caisse-generale/',
        api_views.CaisseGeneraleView.as_view(),
        name='caisse-generale',
    ),
    path(
        'caisse-generale/init/',
        api_views.CaisseGeneraleInitView.as_view(),
        name='caisse-generale-init',
    ),

    # ── Caisse Globale ────────────────────────────────────────────────────
    path(
        'caisse-globale/',
        api_views.CaisseGlobaleListView.as_view(),
        name='caisse-globale-list',
    ),
    path(
        'caisse-globale/ouvrir/',
        api_views.CaisseGlobaleOuvrirView.as_view(),
        name='caisse-globale-ouvrir',
    ),
    path(
        'caisse-globale/active/',
        api_views.CaisseGlobaleActiveView.as_view(),
        name='caisse-globale-active',
    ),
    path(
        'caisse-globale/active/fermer/',
        api_views.CaisseGlobaleFermerView.as_view(),
        name='caisse-globale-fermer',
    ),

    # ── Caisse Comptable ──────────────────────────────────────────────────
    path(
        'caisse-comptable/',
        api_views.CaisseComptableListView.as_view(),
        name='caisse-comptable-list',
    ),
    path(
        'caisse-comptable/ouvrir/',
        api_views.CaisseComptableOuvrirView.as_view(),
        name='caisse-comptable-ouvrir',
    ),
    path(
        'caisse-comptable/active/',
        api_views.CaisseComptableActiveView.as_view(),
        name='caisse-comptable-active',
    ),
    path(
        'caisse-comptable/<int:pk>/',
        api_views.CaisseComptableDetailView.as_view(),
        name='caisse-comptable-detail',
    ),
    path(
        'caisse-comptable/<int:pk>/approvisionner/',
        api_views.CaisseComptableApprovisionnerView.as_view(),
        name='caisse-comptable-approvisionner',
    ),
    path(
        'caisse-comptable/<int:pk>/depense/',
        api_views.DepenseCreateView.as_view(),
        name='caisse-comptable-depense',
    ),
    path(
        'caisse-comptable/<int:pk>/depenses/',
        api_views.DepenseListView.as_view(),
        name='caisse-comptable-depenses',
    ),
    path(
        'caisse-comptable/<int:pk>/fermer/',
        api_views.CaisseComptableFermerView.as_view(),
        name='caisse-comptable-fermer',
    ),

    # ── Remises Serveur ───────────────────────────────────────────────────
    path(
        'remises/',
        api_views.RemiseServeurListView.as_view(),
        name='remise-list',
    ),
    path(
        'remises/<int:pk>/',
        api_views.RemiseServeurDetailView.as_view(),
        name='remise-detail',
    ),
    path(
        'remises/<int:pk>/valider/',
        api_views.RemiseValiderView.as_view(),
        name='remise-valider',
    ),

    # ── Paiements (lecture) ───────────────────────────────────────────────
    path(
        '',
        api_views.PaiementListView.as_view(),
        name='paiement-list',
    ),

    # ── Dashboard Comptable ───────────────────────────────────────────────
    path(
        'dashboard/',
        api_views.DashboardComptableView.as_view(),
        name='dashboard-comptable',
    ),
]
