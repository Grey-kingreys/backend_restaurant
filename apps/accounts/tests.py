"""Tests pour l'app accounts (User, Auth)"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

@pytest.mark.django_db
class TestUserModel:
    """Tests du modèle User"""

    def test_create_user(self):
        """User peut être créé avec login et password"""
        user = User.objects.create_user(
            login="testuser",
            email="test@example.com",
            password="testpass123"
        )
        assert user.id
        assert user.login == "testuser"
        assert user.check_password("testpass123")

    def test_user_login_auto_generation(self, restaurant_factory):
        """login doit être fourni lors de la création"""
        r = restaurant_factory()
        user = User.objects.create_user(
            login="generated_user",
            email="auto@test.com",
            password="pass",
            role="Rserveur",
            restaurant=r
        )
        assert user.login == "generated_user"
        assert user.role == "Rserveur"

    def test_is_admin_role_check(self, restaurant_factory):
        """is_admin() retourne True pour Radmin"""
        r = restaurant_factory()
        admin = User.objects.create_user(
            login="admin", email="a@test.com", password="pass",
            role="Radmin", restaurant=r
        )
        serveur = User.objects.create_user(
            login="serveur", email="s@test.com", password="pass",
            role="Rserveur", restaurant=r
        )

        assert admin.is_admin() is True
        assert serveur.is_admin() is False

@pytest.mark.django_db
class TestAuthAPI:
    """Tests des endpoints /api/accounts/auth/"""

    def test_login_with_email(self, restaurant_factory):
        """Login avec email + password pour staff"""
        r = restaurant_factory()
        user = User.objects.create_user(
            login="admin",
            email="admin@test.com",
            password="correctpass",
            role="Radmin",
            restaurant=r
        )

        client = APIClient()
        res = client.post("/api/accounts/auth/login/", {
            "email": "admin@test.com",
            "password": "correctpass"
        }, format="json")

        assert res.status_code == 200
        assert res.data["success"] is True
        assert "access" in res.data["data"]
        assert "refresh" in res.data["data"]

    def test_login_invalid_credentials(self):
        """Login échoue avec credentials incorrects"""
        client = APIClient()
        res = client.post("/api/accounts/auth/login/", {
            "email": "nonexistent@test.com",
            "password": "wrongpass"
        }, format="json")

        assert res.status_code == 401
        assert res.data["success"] is False

    def test_get_me(self, restaurant_factory):
        """GET /me/ retourne le profil de l'utilisateur connecté"""
        r = restaurant_factory()
        user = User.objects.create_user(
            login="me", email="me@test.com", password="pass",
            role="Radmin", restaurant=r
        )

        refresh = RefreshToken.for_user(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        res = client.get("/api/accounts/auth/me/")

        assert res.status_code == 200
        assert res.data["data"]["login"] == "me"
        assert res.data["data"]["email"] == "me@test.com"

    def test_logout(self, restaurant_factory):
        """Logout blackliste le refresh token"""
        r = restaurant_factory()
        user = User.objects.create_user(
            login="logout_test", email="l@test.com", password="pass",
            role="Radmin", restaurant=r
        )

        refresh = RefreshToken.for_user(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        res = client.post("/api/accounts/auth/logout/", {
            "refresh": str(refresh)
        }, format="json")

        assert res.status_code == 200
        assert res.data["success"] is True

    def test_change_password(self, restaurant_factory):
        """Change password fonctionne avec l'ancien mdp"""
        r = restaurant_factory()
        user = User.objects.create_user(
            login="change_pass", email="cp@test.com", password="oldpass",
            role="Radmin", restaurant=r
        )

        refresh = RefreshToken.for_user(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        res = client.post("/api/accounts/auth/change-password/", {
            "old_password": "oldpass",
            "new_password": "newpass123",
            "new_password_confirm": "newpass123"
        }, format="json")

        assert res.status_code == 200
        user.refresh_from_db()
        assert user.check_password("newpass123")

@pytest.mark.django_db
class TestImpersonationAPI:
    """Tests de l'impersonation"""

    def test_impersonate_user(self, restaurant_factory):
        """Admin peut simuler un autre utilisateur"""
        r = restaurant_factory()
        admin = User.objects.create_user(
            login="admin", email="admin@test.com", password="pass",
            role="Radmin", restaurant=r
        )
        serveur = User.objects.create_user(
            login="serveur", email="serveur@test.com", password="pass",
            role="Rserveur", restaurant=r
        )

        refresh = RefreshToken.for_user(admin)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        res = client.post(f"/api/accounts/auth/users/{serveur.id}/impersonate/", format="json")

        assert res.status_code == 200
        assert res.data["success"] is True
        assert res.data["data"]["user"]["login"] == "serveur"

    def test_cannot_impersonate_admin(self, restaurant_factory):
        """Admin ne peut pas simuler un autre admin"""
        r = restaurant_factory()
        admin1 = User.objects.create_user(
            login="admin1", email="admin1@test.com", password="pass",
            role="Radmin", restaurant=r
        )
        admin2 = User.objects.create_user(
            login="admin2", email="admin2@test.com", password="pass",
            role="Radmin", restaurant=r
        )

        refresh = RefreshToken.for_user(admin1)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        res = client.post(f"/api/accounts/auth/users/{admin2.id}/impersonate/", format="json")

        assert res.status_code == 403

    def test_cannot_impersonate_different_restaurant(self, restaurant_factory):
        """Admin ne peut simuler que dans son restaurant"""
        r1 = restaurant_factory(nom="R1")
        r2 = restaurant_factory(nom="R2")

        admin1 = User.objects.create_user(
            login="admin1", email="a1@test.com", password="pass",
            role="Radmin", restaurant=r1
        )
        user2 = User.objects.create_user(
            login="user2", email="u2@test.com", password="pass",
            role="Rserveur", restaurant=r2
        )

        refresh = RefreshToken.for_user(admin1)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        res = client.post(f"/api/accounts/auth/users/{user2.id}/impersonate/", format="json")

        assert res.status_code == 403


@pytest.mark.django_db
class TestUserCreateSerializer:
    """Le mot de passe initial est obligatoire — pas d'auto-génération.

    Régression : password était `required=False`, donc un mot de passe vide
    produisait un compte à mot de passe inutilisable (connexion impossible).
    """

    def _serializer(self, creator, data):
        from apps.accounts.serializers import UserCreateSerializer
        from rest_framework.test import APIRequestFactory
        req = APIRequestFactory().post("/")
        req.user = creator
        return UserCreateSerializer(data=data, context={"request": req})

    def _admin(self, restaurant_factory):
        return User.objects.create_user(
            login="admin", email="a@test.com", password="pass",
            role="Radmin", restaurant=restaurant_factory(),
        )

    def test_password_manquant_refuse(self, restaurant_factory):
        admin = self._admin(restaurant_factory)
        s = self._serializer(admin, {
            "role": "Rserveur", "nom_complet": "Awa Diallo", "email": "awa@test.com",
        })
        assert not s.is_valid()
        assert "password" in s.errors

    def test_password_trop_court_refuse(self, restaurant_factory):
        admin = self._admin(restaurant_factory)
        s = self._serializer(admin, {
            "role": "Rserveur", "nom_complet": "Awa Diallo",
            "email": "awa@test.com", "password": "court",
        })
        assert not s.is_valid()
        assert "password" in s.errors

    def test_password_valide_cree_compte_utilisable(self, restaurant_factory):
        admin = self._admin(restaurant_factory)
        s = self._serializer(admin, {
            "role": "Rserveur", "nom_complet": "Awa Diallo",
            "email": "awa@test.com", "password": "MotDePasse1",
        })
        assert s.is_valid(), s.errors
        user = s.save()
        assert user.has_usable_password() is True
        assert user.check_password("MotDePasse1")
        assert user.must_change_password is True
