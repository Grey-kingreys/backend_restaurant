"""Les quatre flux d'émission de jetons posent les mêmes claims."""
import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import User
from apps.accounts.tests import _attach_role_config
from apps.restaurant.models import TableToken


def _verifier_claims(access, user):
    payload = AccessToken(access).payload
    assert payload["role"] == user.role
    assert payload["nom_complet"] == user.nom_complet
    assert payload["restaurant_id"] == user.restaurant_id


@pytest.mark.django_db
def test_login_pose_les_claims(restaurant_factory):
    serveur = User.objects.create_user(
        login="serveur", email="serveur@test.com", password="correctpass",
        role="Rserveur", restaurant=restaurant_factory(),
    )
    res = APIClient().post(
        "/api/accounts/auth/login/",
        {"email": "serveur@test.com", "password": "correctpass"}, format="json",
    )
    assert res.status_code == 200
    _verifier_claims(res.data["data"]["access"], serveur)


@pytest.mark.django_db
def test_inscription_client_pose_les_claims_restaurant_null():
    res = APIClient().post(
        "/api/public/auth/register/",
        {
            "email": "client@test.com", "password": "motdepasse123",
            "password_confirm": "motdepasse123", "nom_complet": "Client Test",
            "telephone": "620000001",
        },
        format="json",
    )
    assert res.status_code == 201
    access = res.data["data"]["access"]
    assert AccessToken(access).payload["restaurant_id"] is None
    _verifier_claims(access, User.objects.get(email="client@test.com"))


@pytest.mark.django_db
def test_connexion_qr_pose_les_claims(restaurant_factory):
    table = User.objects.create_user(
        login="table_01", email=None, password="pass",
        role="Rtable", restaurant=restaurant_factory(),
    )
    token = TableToken.generer_token(table).token
    res = APIClient().post(f"/api/accounts/qr/{token}/", {}, format="json")
    assert res.status_code == 200
    _verifier_claims(res.data["data"]["access"], table)


@pytest.mark.django_db
def test_simulation_pose_les_claims(restaurant_factory):
    resto = restaurant_factory()
    admin = User.objects.create_user(
        login="admin", email="admin@test.com", password="pass",
        role="Radmin", restaurant=resto,
    )
    _attach_role_config(admin)
    serveur = User.objects.create_user(
        login="serveur", email="serveur@test.com", password="pass",
        role="Rserveur", restaurant=resto,
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(admin).access_token}")
    res = client.post(f"/api/accounts/auth/users/{serveur.id}/impersonate/", format="json")
    assert res.status_code == 200
    _verifier_claims(res.data["data"]["access"], serveur)
