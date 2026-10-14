"""L'alias /api/v1/ sert les mêmes routes que /api/."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.mark.django_db
def test_liste_restaurants_identique_sous_v1(restaurant_factory):
    restaurant_factory(nom="Le Baobab", accept_livraison=True)
    api = APIClient()
    ancienne = api.get("/api/public/restaurants/")
    v1 = api.get("/api/v1/public/restaurants/")
    assert v1.status_code == ancienne.status_code == 200
    assert v1.json() == ancienne.json()


@pytest.mark.django_db
def test_route_authentifiee_sous_v1(restaurant_factory):
    User.objects.create_user(
        login="serveur", email="serveur@test.com", password="correctpass",
        role="Rserveur", restaurant=restaurant_factory(),
    )
    api = APIClient()
    connexion = api.post(
        "/api/v1/accounts/auth/login/",
        {"email": "serveur@test.com", "password": "correctpass"}, format="json",
    )
    assert connexion.status_code == 200
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {connexion.data['data']['access']}")
    moi = api.get("/api/v1/accounts/auth/me/")
    assert moi.status_code == 200
    assert moi.json()["data"]["email"] == "serveur@test.com"
