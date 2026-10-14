import pytest
from rest_framework.test import APIClient

from apps.commandes.models import Commande, CommandeItem
from apps.menu.models import Plat


@pytest.fixture
def commande_client(user_factory, restaurant_factory):
    resto = restaurant_factory(nom="Le Baobab", accept_livraison=True, accept_emporter=True)
    plat = Plat.objects.create(restaurant=resto, nom="Poulet braisé", prix_unitaire=50000)
    client_user = user_factory(
        login="client_test", email="client@test.com", role="Rclient", restaurant=None,
    )
    api = APIClient()
    api.force_authenticate(client_user)
    return api, resto, plat


def _commander(api, resto, plat, quantite):
    return api.post(
        f"/api/public/restaurants/{resto.get_slug()}/commander/",
        {
            "type_commande": "emporter",
            "mode_paiement": "livraison",
            "telephone": "620000000",
            "items": [{"plat_id": plat.id, "quantite": quantite}],
        },
        format="json",
    )


@pytest.mark.django_db
@pytest.mark.parametrize("quantite", ["abc", 0, 51, 2.5, "2.5", -1, None, True, [], ""])
def test_commander_quantite_invalide_renvoie_400(commande_client, quantite):
    api, resto, plat = commande_client
    reponse = _commander(api, resto, plat, quantite)
    assert reponse.status_code == 400
    corps = reponse.json()
    assert corps["success"] is False
    assert "entier entre 1 et 50" in corps["errors"]["items"][0]
    assert not Commande.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("quantite", [3, "3", 1, 50])
def test_commander_quantite_valide_cree_la_commande(commande_client, quantite):
    api, resto, plat = commande_client
    reponse = _commander(api, resto, plat, quantite)
    assert reponse.status_code == 201
    assert CommandeItem.objects.get().quantite == int(quantite)


@pytest.fixture
def cache_vide():
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


def _inscrire(api, n):
    return api.post(
        "/api/public/auth/register/",
        {
            "email": f"nouveau{n}@test.com",
            "password": "motdepasse123",
            "password_confirm": "motdepasse123",
            "nom_complet": f"Client {n}",
            "telephone": f"62000000{n}",
        },
        format="json",
    )


@pytest.mark.django_db
def test_inscription_limitee_a_5_par_heure_et_par_ip(cache_vide):
    api = APIClient()
    for n in range(5):
        assert _inscrire(api, n).status_code == 201
    reponse = _inscrire(api, 5)
    assert reponse.status_code == 429
    assert reponse.json()["success"] is False


def test_cache_utilise_redis_hors_test():
    import importlib
    import os
    from unittest import mock
    with mock.patch.dict(os.environ, {"REDIS_URL": "redis://exemple:6379/1"}):
        import backend.settings as reglages
        reglages = importlib.reload(reglages)
        assert reglages.CACHES["default"]["BACKEND"].endswith("redis.RedisCache")
        assert reglages.CACHES["default"]["LOCATION"] == "redis://exemple:6379/1"
    importlib.reload(reglages)
