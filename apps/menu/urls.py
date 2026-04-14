# apps/menu/urls.py
from django.urls import path
from . import api_views

app_name = 'menu'

urlpatterns = [
    # Catégories (avant <pk> pour éviter le conflit de routage)
    path(
        'plats/categories/',
        api_views.PlatCategoriesView.as_view(),
        name='plat-categories'
    ),

    # Liste + Création
    path(
        'plats/',
        api_views.PlatListCreateView.as_view(),
        name='plat-list-create'
    ),

    # Détail + Modification
    path(
        'plats/<int:pk>/',
        api_views.PlatDetailView.as_view(),
        name='plat-detail'
    ),

    # Toggle disponibilité
    path(
        'plats/<int:pk>/toggle/',
        api_views.PlatToggleView.as_view(),
        name='plat-toggle'
    ),
]