"""Tests pour l'app company (Restaurant, OnboardingToken)"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from apps.company.models import Restaurant, OnboardingToken
from apps.accounts.serializers import get_role_config_for_role

User = get_user_model()


def _attach_role_config(user):
    """Assigne le RoleConfig système du rôle (comme en prod via l'API/seed).

    create_user() ne le fait pas ; sans role_config, has_permission() renvoie
    toujours False. Les vues gatées par permission l'exigent.
    """
    user.role_config = get_role_config_for_role(user.role)
    user.save(update_fields=["role_config"])
    return user

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

        refresh = RefreshToken.for_user(superadmin_user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        res = client.get("/api/company/restaurants/")

        assert res.status_code == 200
        assert res.data["success"] is True
        assert res.data["data"]["count"] >= 2

    def test_create_restaurant_superadmin_only(self, superadmin_user):
        """Seul Super Admin peut créer un restaurant"""
        refresh = RefreshToken.for_user(superadmin_user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        payload = {
            "nom": "Nouveau Restaurant",
            "email_admin": "admin@new.com",
            "telephone": "+224620000000",
        }
        res = client.post("/api/company/restaurants/", payload, format="json")

        assert res.status_code == 201
        assert res.data["success"] is True
        assert Restaurant.objects.filter(nom="Nouveau Restaurant").exists()

    def test_get_restaurant_detail(self, superadmin_user, restaurant_factory):
        """Récupérer les détails d'un restaurant"""
        r = restaurant_factory(nom="Detail Test")
        refresh = RefreshToken.for_user(superadmin_user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        res = client.get(f"/api/company/restaurants/{r.id}/")

        assert res.status_code == 200
        assert res.data["data"]["nom"] == "Detail Test"

    def test_patch_restaurant(self, superadmin_user, restaurant_factory):
        """Modifier un restaurant (PATCH)"""
        r = restaurant_factory(nom="Old Name")
        refresh = RefreshToken.for_user(superadmin_user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        res = client.patch(f"/api/company/restaurants/{r.id}/", {
            "nom": "New Name"
        }, format="json")

        assert res.status_code == 200
        r.refresh_from_db()
        assert r.nom == "New Name"

    def test_suspend_restaurant(self, superadmin_user, restaurant_factory):
        """Suspendre un restaurant"""
        r = restaurant_factory(is_active=True)
        refresh = RefreshToken.for_user(superadmin_user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        res = client.post(f"/api/company/restaurants/{r.id}/suspend/", format="json")

        assert res.status_code == 200
        r.refresh_from_db()
        assert r.is_active is False

    def test_activate_restaurant(self, superadmin_user, restaurant_factory):
        """Réactiver un restaurant"""
        r = restaurant_factory(is_active=False)
        refresh = RefreshToken.for_user(superadmin_user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        res = client.post(f"/api/company/restaurants/{r.id}/activate/", format="json")

        assert res.status_code == 200
        r.refresh_from_db()
        assert r.is_active is True

@pytest.mark.django_db
class TestMonRestaurantAPI:
    """Tests de /api/company/mon-restaurant/"""

    def test_get_mon_restaurant_admin_only(self, restaurant_factory):
        """L'admin (permission manage_restaurant) peut voir son restaurant"""
        r = restaurant_factory()
        admin = _attach_role_config(User.objects.create_user(
            login="admin", email="a@test.com", password="pass",
            role="Radmin", restaurant=r
        ))

        refresh = RefreshToken.for_user(admin)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        res = client.get("/api/company/mon-restaurant/")

        assert res.status_code == 200
        assert res.data["data"]["id"] == r.id

    def test_patch_mon_restaurant(self, restaurant_factory):
        """Admin peut modifier son restaurant"""
        r = restaurant_factory(nom="Old")
        admin = _attach_role_config(User.objects.create_user(
            login="admin", email="a@test.com", password="pass",
            role="Radmin", restaurant=r
        ))

        refresh = RefreshToken.for_user(admin)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        res = client.patch("/api/company/mon-restaurant/", {
            "nom": "Updated"
        }, format="json")

        assert res.status_code == 200
        r.refresh_from_db()
        assert r.nom == "Updated"

    def test_patch_mon_restaurant_persiste_geolocalisation(self, restaurant_factory):
        """Régression : latitude/longitude/rayon/durée doivent être enregistrés.

        Ces champs étaient absents de MonRestaurantUpdateSerializer.Meta.fields :
        DRF les ignorait silencieusement, donc la position n'était jamais sauvegardée.
        """
        r = restaurant_factory(nom="Geo")
        admin = _attach_role_config(User.objects.create_user(
            login="admin", email="a@test.com", password="pass",
            role="Radmin", restaurant=r
        ))

        refresh = RefreshToken.for_user(admin)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        res = client.patch("/api/company/mon-restaurant/", {
            "latitude": 9.641185,
            "longitude": -13.578401,
            "rayon_connexion": 350,
            "duree_session_table": 90,
        }, format="json")

        assert res.status_code == 200
        r.refresh_from_db()
        assert float(r.latitude) == pytest.approx(9.641185)
        assert float(r.longitude) == pytest.approx(-13.578401)
        assert r.rayon_connexion == 350
        assert r.duree_session_table == 90

    def test_patch_mon_restaurant_rejette_coordonnees_invalides(self, restaurant_factory):
        """Une latitude hors bornes est refusée (400) et rien n'est enregistré."""
        r = restaurant_factory(nom="GeoKO")
        admin = _attach_role_config(User.objects.create_user(
            login="admin", email="a@test.com", password="pass",
            role="Radmin", restaurant=r
        ))

        refresh = RefreshToken.for_user(admin)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        res = client.patch("/api/company/mon-restaurant/", {
            "latitude": 200,
            "longitude": 0,
        }, format="json")

        assert res.status_code == 400
        r.refresh_from_db()
        assert r.latitude is None

    def test_get_mon_restaurant_manager_autorise(self, restaurant_factory):
        """Le manager a la permission manage_restaurant → accès autorisé (GET)."""
        r = restaurant_factory()
        manager = _attach_role_config(User.objects.create_user(
            login="manager", email="m@test.com", password="pass",
            role="Rmanager", restaurant=r
        ))

        refresh = RefreshToken.for_user(manager)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        res = client.get("/api/company/mon-restaurant/")

        assert res.status_code == 200
        assert res.data["data"]["id"] == r.id

    def test_patch_mon_restaurant_manager_autorise(self, restaurant_factory):
        """Le manager peut aussi modifier le restaurant (PATCH)."""
        r = restaurant_factory(nom="Avant")
        manager = _attach_role_config(User.objects.create_user(
            login="manager", email="m@test.com", password="pass",
            role="Rmanager", restaurant=r
        ))

        refresh = RefreshToken.for_user(manager)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        res = client.patch("/api/company/mon-restaurant/", {"nom": "Apres"}, format="json")

        assert res.status_code == 200
        r.refresh_from_db()
        assert r.nom == "Apres"

    def test_mon_restaurant_refuse_sans_permission(self, restaurant_factory):
        """Un rôle sans manage_restaurant (serveur) reçoit 403."""
        r = restaurant_factory()
        serveur = _attach_role_config(User.objects.create_user(
            login="serveur", email="s@test.com", password="pass",
            role="Rserveur", restaurant=r
        ))

        refresh = RefreshToken.for_user(serveur)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        assert client.get("/api/company/mon-restaurant/").status_code == 403
        assert client.patch(
            "/api/company/mon-restaurant/", {"nom": "X"}, format="json"
        ).status_code == 403


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
        refresh = RefreshToken.for_user(admin)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        res = client.get("/api/company/stats/")
        assert res.status_code == 403

        # Super Admin peut accéder
        refresh_sa = RefreshToken.for_user(superadmin)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh_sa.access_token}")
        res = client.get("/api/company/stats/")
        assert res.status_code == 200
        assert res.data["success"] is True
        assert res.data["data"]["restaurants_total"] >= 3
