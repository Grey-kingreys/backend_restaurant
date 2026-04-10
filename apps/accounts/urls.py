# apps/accounts/urls.py
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import api_views

app_name = 'accounts'

urlpatterns = [

    # ── Auth ──────────────────────────────────────────────────────────────
    path(
        'auth/login/',
        api_views.LoginView.as_view(),
        name='login'
    ),
    path(
        'auth/logout/',
        api_views.LogoutView.as_view(),
        name='logout'
    ),
    path(
        'auth/token/refresh/',
        TokenRefreshView.as_view(),
        name='token-refresh'
    ),
    path(
        'auth/me/',
        api_views.MeView.as_view(),
        name='me'
    ),
    path(
        'auth/change-password/',
        api_views.ChangePasswordView.as_view(),
        name='change-password'
    ),

    # ── CRUD Utilisateurs ─────────────────────────────────────────────────
    path(
        'auth/users/',
        api_views.UserListCreateView.as_view(),
        name='user-list-create'
    ),
    path(
        'auth/users/<int:pk>/',
        api_views.UserDetailView.as_view(),
        name='user-detail'
    ),
    path(
        'auth/users/<int:pk>/toggle/',
        api_views.UserToggleView.as_view(),
        name='user-toggle'
    ),
    path(
        'auth/users/<int:pk>/reset-password/',
        api_views.AdminPasswordResetView.as_view(),
        name='user-reset-password'
    ),

    # ── Reset mot de passe (self-service) ─────────────────────────────────
    path(
        'auth/password/reset-request/',
        api_views.PasswordResetRequestView.as_view(),
        name='password-reset-request'
    ),
    path(
        'auth/password/reset-confirm/',
        api_views.PasswordResetConfirmView.as_view(),
        name='password-reset-confirm'
    ),
]