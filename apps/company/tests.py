"""Tests pour l'app company (Restaurant, OnboardingToken)"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from apps.company.models import Restaurant, OnboardingToken

User = get_user_model()

@pytest.mark.django_db
class TestRestaurantModel:
    """Tests du modèle Restaurant"""

    def test_create_restaurant(self):
        """Restaurant peut être créé avec les champs requis"""
        restaurant = Restaurant.objects.create(
            nom="Le Baobab",
            is_active=True
        )
        assert restaurant.id
        assert restaurant.nom == "Le Baobab"
        assert restaurant.is_active is True

    def test_get_slug(self):
        """get_slug() retourne le slug du restaurant"""
        restaurant = Restaurant.objects.create(nom="Le Baobab")
        assert restaurant.get_slug() == "lebaobab"

    def test_suspendre_restaurant(self):
        """suspendre() passe is_active à False"""
        restaurant = Restaurant.objects.create(nom="Test", is_active=True)
        restaurant.suspendre()
        assert restaurant.is_active is False

    def test_reactiver_restaurant(self):
        """reactiver() passe is_active à True"""
        restaurant = Restaurant.objects.create(nom="Test", is_active=False)
        restaurant.reactiver()
        assert restaurant.is_active is True

@pytest.mark.django_db
class TestRestaurantAPI:
    """Tests des endpoints /api/company/restaurants/"""

    @pytest.fixture
    def superadmin_user(self):
        return User.objects.create_user(
            login="superadmin",
            email="sa@test.com",
            password="pass123",
            role="Rsuper_admin"
        )

    @pytest.fixture
    def admin_user(self, restaurant_factory):
        r = restaurant_factory()
        return User.objects.create_user(
            login="admin",
            email="admin@test.com",
            password="pass123",
            role="Radmin",
            restaurant=r
        )

    def test_list_restaurants_superadmin_only(self, superadmin_user, admin_user, restaurant_factory):
        """Seul Super Admin peut lister tous les restaurants"""
        restaurant_factory()
        restaurant_factory()

        client = APIClient()
        client.force_login(superadmin_user)
        res = client.get("/api/company/restaurants/")

        assert res.status_code == 200
        assert res.data["success"] is True
        assert res.data["data"]["count"] >= 2

    def test_create_restaurant_superadmin_only(self, superadmin_user):
        """Seul Super Admin peut créer un restaurant"""
        client = APIClient()
        client.force_login(superadmin_user)

        payload = {
            "nom": "Nouveau Restaurant",
            "email_admin": "admin@new.com"
        }
        res = client.post("/api/company/restaurants/", payload, format="json")

        assert res.status_code == 201
        assert res.data["success"] is True
        assert Restaurant.objects.filter(nom="Nouveau Restaurant").exists()

    def test_get_restaurant_detail(self, superadmin_user, restaurant_factory):
        """Récupérer les détails d'un restaurant"""
        r = restaurant_factory(nom="Detail Test")
        client = APIClient()
        client.force_login(superadmin_user)

        res = client.get(f"/api/company/restaurants/{r.id}/")

        assert res.status_code == 200
        assert res.data["data"]["nom"] == "Detail Test"

    def test_patch_restaurant(self, superadmin_user, restaurant_factory):
        """Modifier un restaurant (PATCH)"""
        r = restaurant_factory(nom="Old Name")
        client = APIClient()
        client.force_login(superadmin_user)

        res = client.patch(f"/api/company/restaurants/{r.id}/", {
            "nom": "New Name"
        }, format="json")

        assert res.status_code == 200
        r.refresh_from_db()
        assert r.nom == "New Name"

    def test_suspend_restaurant(self, superadmin_user, restaurant_factory):
        """Suspendre un restaurant"""
        r = restaurant_factory(is_active=True)
        client = APIClient()
        client.force_login(superadmin_user)

        res = client.post(f"/api/company/restaurants/{r.id}/suspend/", format="json")

        assert res.status_code == 200
        r.refresh_from_db()
        assert r.is_active is False

    def test_activate_restaurant(self, superadmin_user, restaurant_factory):
        """Réactiver un restaurant"""
        r = restaurant_factory(is_active=False)
        client = APIClient()
        client.force_login(superadmin_user)

        res = client.post(f"/api/company/restaurants/{r.id}/activate/", format="json")

        assert res.status_code == 200
        r.refresh_from_db()
        assert r.is_active is True

@pytest.mark.django_db
class TestMonRestaurantAPI:
    """Tests de /api/company/mon-restaurant/"""

    def test_get_mon_restaurant_admin_only(self, restaurant_factory):
        """Seul l'admin peut voir son restaurant"""
        r = restaurant_factory()
        admin = User.objects.create_user(
            login="admin", email="a@test.com", password="pass",
            role="Radmin", restaurant=r
        )

        client = APIClient()
        client.force_login(admin)
        res = client.get("/api/company/mon-restaurant/")

        assert res.status_code == 200
        assert res.data["data"]["id"] == r.id

    def test_patch_mon_restaurant(self, restaurant_factory):
        """Admin peut modifier son restaurant"""
        r = restaurant_factory(nom="Old")
        admin = User.objects.create_user(
            login="admin", email="a@test.com", password="pass",
            role="Radmin", restaurant=r
        )

        client = APIClient()
        client.force_login(admin)
        res = client.patch("/api/company/mon-restaurant/", {
            "nom": "Updated"
        }, format="json")

        assert res.status_code == 200
        r.refresh_from_db()
        assert r.nom == "Updated"

@pytest.mark.django_db
class TestPlatformStatsAPI:
    """Tests de /api/company/stats/"""

    def test_platform_stats_superadmin_only(self, restaurant_factory):
        """Seul Super Admin peut voir les stats"""
        restaurant_factory(nom="R1")
        restaurant_factory(nom="R2")

        admin = User.objects.create_user(
            login="admin", email="a@test.com", password="pass",
            role="Radmin", restaurant=restaurant_factory()
        )

        superadmin = User.objects.create_user(
            login="sa", email="sa@test.com", password="pass",
            role="Rsuper_admin"
        )

        client = APIClient()

        # Admin ne peut pas accéder
        client.force_login(admin)
        res = client.get("/api/company/stats/")
        assert res.status_code == 403

        # Super Admin peut accéder
        client.force_login(superadmin)
        res = client.get("/api/company/stats/")
        assert res.status_code == 200
        assert res.data["success"] is True
        assert res.data["data"]["restaurants_total"] >= 3
