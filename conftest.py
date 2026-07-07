"""Root conftest.py — pytest fixtures for Django + DRF"""
import os
import django
from django.conf import settings
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

@pytest.fixture(scope="session")
def django_db_setup():
    """Override default test database settings"""
    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "ATOMIC_REQUESTS": False,
    }

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
