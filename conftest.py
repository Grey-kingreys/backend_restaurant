"""Root conftest.py — pytest fixtures for Django + DRF"""
import os

# Force les settings de test AVANT que pytest-django ne configure Django.
# L'image Docker fixe DJANGO_SETTINGS_MODULE=backend.settings (Dockerfile), ce qui
# écrasait le settings de pytest.ini. On le rétablit ici, tôt dans le démarrage de
# pytest, pour garantir MD5 hasher / Celery eager / logs silencieux en test.
os.environ["DJANGO_SETTINGS_MODULE"] = "backend.test_settings"

import django
from django.conf import settings
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

# NOTE : pas d'override de `django_db_setup`. On laisse pytest-django créer une
# vraie base de test isolée (`test_backend_db`) sur PostgreSQL via setup_databases()
# — migrations fraîches, chaque test en transaction annulée. L'ancien hack qui
# forçait sqlite `:memory:` était racé (ne s'appliquait que si la connexion Postgres
# n'était pas déjà ouverte) et faisait tourner les tests sur la base seedée `backend_db`.
# PostgreSQL est requis de toute façon : `select_for_update()` / `F()` des tests de
# soldes de caisse ne sont significatifs que sur le même moteur qu'en prod.

@pytest.fixture
def restaurant_factory(db):
    """Factory for creating Restaurant instances"""
    from apps.company.models import Restaurant

    def create_restaurant(nom="Test Restaurant", is_active=True, **kwargs):
        return Restaurant.objects.create(nom=nom, is_active=is_active, **kwargs)

    return create_restaurant

@pytest.fixture
def user_factory(db, restaurant_factory):
    """Factory for creating User instances"""

    def create_user(
        login="testuser",
        email="test@example.com",
        password="testpass123",
        role="Rserveur",
        restaurant=None,
        **kwargs
    ):
        if restaurant is None and role != "Rsuper_admin":
            restaurant = restaurant_factory()

        user = User.objects.create_user(
            login=login,
            email=email,
            password=password,
            role=role,
            restaurant=restaurant,
            **kwargs
        )
        return user

    return create_user

@pytest.fixture
def authenticated_client(client, user_factory):
    """Returns an authenticated test client"""
    user = user_factory(login="admin", email="admin@test.com", role="Radmin")
    client.force_login(user)
    return client, user

@pytest.fixture
def superadmin_client(client, user_factory):
    """Returns a Super Admin authenticated test client"""
    user = user_factory(login="superadmin", email="sa@test.com", role="Rsuper_admin", restaurant=None)
    client.force_login(user)
    return client, user

@pytest.fixture
def api_client():
    """Returns a DRF API test client with JWT token support"""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    class AuthenticatedAPIClient(APIClient):
        def _authenticate(self, user):
            refresh = RefreshToken.for_user(user)
            self.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    return AuthenticatedAPIClient()

@pytest.fixture
def authenticated_api_client(api_client, user_factory):
    """API client authenticated as admin"""
    user = user_factory(login="admin_api", email="admin@api.com", role="Radmin")
    api_client._authenticate(user)
    return api_client, user
