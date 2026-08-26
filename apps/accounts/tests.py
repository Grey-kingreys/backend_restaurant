"""Tests pour l'app accounts (User, Auth)"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from apps.accounts.serializers import get_role_config_for_role

User = get_user_model()


def _attach_role_config(user):
    """Assigne le RoleConfig système du rôle (comme en prod via l'API/seed).

    create_user() ne le fait pas ; sans role_config, has_permission() renvoie
    toujours False et les vues gatées par permission renvoient 403. Nécessaire
    pour tester les vraies règles métier (et non le seul refus de permission).
    """
    user.role_config = get_role_config_for_role(user.role)
    user.save(update_fields=["role_config"])

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

        # Le LoginView valide les identifiants via un serializer → 400 (contrat
        # OpenAPI documenté « 400 : Identifiants invalides »), pas 401.
        assert res.status_code == 400
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
        _attach_role_config(admin)
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
        _attach_role_config(admin1)
        admin2 = User.objects.create_user(
            login="admin2", email="admin2@test.com", password="pass",
            role="Radmin", restaurant=r
        )

        refresh = RefreshToken.for_user(admin1)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        res = client.post(f"/api/accounts/auth/users/{admin2.id}/impersonate/", format="json")

        # admin1 A la permission d'impersonation : c'est bien la règle métier
        # (cible = Admin) qui doit bloquer → 400, pas un refus de permission.
        assert res.status_code == 400

    def test_cannot_impersonate_different_restaurant(self, restaurant_factory):
        """Admin ne peut simuler que dans son restaurant"""
        r1 = restaurant_factory(nom="R1")
        r2 = restaurant_factory(nom="R2")

        admin1 = User.objects.create_user(
            login="admin1", email="a1@test.com", password="pass",
            role="Radmin", restaurant=r1
        )
        _attach_role_config(admin1)
        user2 = User.objects.create_user(
            login="user2", email="u2@test.com", password="pass",
            role="Rserveur", restaurant=r2
        )

        refresh = RefreshToken.for_user(admin1)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        res = client.post(f"/api/accounts/auth/users/{user2.id}/impersonate/", format="json")

        # admin1 A la permission : la cible d'un AUTRE restaurant est simplement
        # introuvable dans son périmètre (get_object_or_404) → 404.
        assert res.status_code == 404


@pytest.mark.django_db
class TestUserCreateSerializer:
    """Le mot de passe initial est obligatoire - pas d'auto-génération.

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


@pytest.mark.django_db
class TestRoleConfigSecurity:
    """Sécurité de l'endpoint /api/accounts/roles/<pk>/.

    Régression : la garde `if not role.is_system and role.restaurant != ...`
    court-circuitait pour les rôles système (is_system=True, restaurant=None,
    partagés par TOUS les tenants). Un Radmin avec `manage_roles` pouvait donc
    PATCH/DELETE un rôle système et impacter tous les restaurants du SaaS.
    Les rôles système doivent renvoyer 403 ; le custom d'un autre tenant, 404.
    """

    def _admin(self, restaurant_factory):
        from apps.accounts.models import RoleConfig
        admin = User.objects.create_user(
            login="radmin", email="ra@test.com", password="pass",
            role="Radmin", restaurant=restaurant_factory(),
        )
        # role_config = rôle système Radmin (porte la permission manage_roles)
        admin.role_config = RoleConfig.objects.get(slug="Radmin", is_system=True)
        admin.save(update_fields=["role_config"])
        assert admin.has_permission("manage_roles")
        return admin

    def _client(self, user):
        refresh = RefreshToken.for_user(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        return client

    def test_patch_role_systeme_interdit(self, restaurant_factory):
        from apps.accounts.models import RoleConfig
        admin = self._admin(restaurant_factory)
        sys_role = RoleConfig.objects.get(slug="Rserveur", is_system=True)
        res = self._client(admin).patch(
            f"/api/accounts/roles/{sys_role.id}/", {"nom": "PWNED"}, format="json"
        )
        assert res.status_code == 403
        sys_role.refresh_from_db()
        assert sys_role.nom != "PWNED"

    def test_delete_role_systeme_interdit(self, restaurant_factory):
        from apps.accounts.models import RoleConfig
        admin = self._admin(restaurant_factory)
        sys_role = RoleConfig.objects.get(slug="Rcomptable", is_system=True)
        res = self._client(admin).delete(f"/api/accounts/roles/{sys_role.id}/")
        assert res.status_code == 403
        assert RoleConfig.objects.filter(id=sys_role.id).exists()

    def test_patch_role_custom_autre_tenant_404(self, restaurant_factory):
        from apps.accounts.models import RoleConfig
        admin = self._admin(restaurant_factory)
        autre = restaurant_factory(nom="Autre resto")
        role_autre = RoleConfig.objects.create(
            restaurant=autre, nom="Custom", slug="custom_autre",
            is_system=False, dashboard_type="serveur",
        )
        res = self._client(admin).patch(
            f"/api/accounts/roles/{role_autre.id}/", {"nom": "PWNED"}, format="json"
        )
        assert res.status_code == 404
        role_autre.refresh_from_db()
        assert role_autre.nom == "Custom"


@pytest.mark.django_db
class TestMessageEmailDejaPris:
    """
    Message d'unicite d'email a la creation d'un membre.

    `User.email` est unique sur toute la plateforme, alors que la page Equipe
    ne liste que les membres ACTIFS du restaurant courant. Le compte fautif est
    donc souvent invisible pour l'admin, qui lisait « Un objet Utilisateur avec
    ce champ Adresse email existe deja. » sans pouvoir le trouver nulle part.
    """

    URL = "/api/accounts/auth/users/"

    def _admin(self, restaurant_factory, user_factory):
        from apps.accounts.serializers import get_role_config_for_role
        resto = restaurant_factory(nom="Resto Email")
        admin = user_factory(login="adm_mail", email="adm_mail@t.gn",
                             role="Radmin", restaurant=resto)
        admin.role_config = get_role_config_for_role("Radmin")
        admin.save(update_fields=["role_config"])
        return resto, admin

    def _creer(self, api_client, email):
        return api_client.post(self.URL, {
            "role": "Rserveur", "nom_complet": "Nouveau", "email": email,
            "telephone": "+224620000222", "password": "Users@2026",
        }, format="json")

    def test_email_dun_compte_client_designe_le_compte_client(
        self, api_client, user_factory, restaurant_factory
    ):
        resto, admin = self._admin(restaurant_factory, user_factory)
        User.objects.create_user(login="cli_x", email="client@x.gn",
                                 role="Rclient", restaurant=None, password="x")
        api_client._authenticate(admin)

        res = self._creer(api_client, "client@x.gn")

        assert res.status_code == 400
        assert "compte client" in res.data["errors"]["email"][0]

    def test_email_dun_membre_desactive_invite_a_le_reactiver(
        self, api_client, user_factory, restaurant_factory
    ):
        resto, admin = self._admin(restaurant_factory, user_factory)
        m = user_factory(login="off_x", email="off@x.gn", role="Rserveur",
                         restaurant=resto, nom_complet="Fatou Camara")
        m.actif = False
        m.save(update_fields=["actif"])
        api_client._authenticate(admin)

        res = self._creer(api_client, "off@x.gn")

        assert res.status_code == 400
        msg = res.data["errors"]["email"][0]
        assert "Fatou Camara" in msg and "desactive" in msg

    def test_email_dun_autre_restaurant_ne_nomme_personne(
        self, api_client, user_factory, restaurant_factory
    ):
        resto, admin = self._admin(restaurant_factory, user_factory)
        voisin = restaurant_factory(nom="Resto Voisin Email")
        user_factory(login="voisin_x", email="voisin@x.gn", role="Rserveur",
                     restaurant=voisin, nom_complet="Secret Personne")
        api_client._authenticate(admin)

        res = self._creer(api_client, "voisin@x.gn")

        assert res.status_code == 400
        msg = res.data["errors"]["email"][0]
        # Pas de fuite d'identite d'un compte tiers.
        assert "Secret Personne" not in msg
        assert "ailleurs sur la plateforme" in msg

    def test_message_technique_de_drf_ne_remonte_plus(
        self, api_client, user_factory, restaurant_factory
    ):
        resto, admin = self._admin(restaurant_factory, user_factory)
        api_client._authenticate(admin)

        res = self._creer(api_client, admin.email)

        assert res.status_code == 400
        assert "objet Utilisateur" not in res.data["errors"]["email"][0]
