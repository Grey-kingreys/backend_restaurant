import pytest
from django.test import override_settings
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


@pytest.mark.django_db
@pytest.mark.parametrize("frontend_url", ["https://resfly.org", "https://resfly.org/"])
def test_commander_suivi_url_absolue_sans_double_barre(commande_client, frontend_url):
    from django.test import override_settings

    api, resto, plat = commande_client
    with override_settings(FRONTEND_URL=frontend_url):
        reponse = _commander(api, resto, plat, 1)
    assert reponse.status_code == 201
    suivi_url = reponse.json()["data"]["suivi_url"]
    cle = reponse.json()["data"]["cle_suivi"]
    assert suivi_url == f"https://resfly.org/restaurant/{resto.get_slug()}/confirmation/{cle}/"
    assert "//" not in suivi_url.split("://", 1)[1]


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


@pytest.mark.django_db
@pytest.mark.parametrize("mot_de_passe", ["12345678", "password", "abc"])
def test_inscription_refuse_mot_de_passe_faible_avec_message_francais(cache_vide, mot_de_passe):
    api = APIClient()
    reponse = api.post(
        "/api/public/auth/register/",
        {
            "email": "faible@test.com",
            "password": mot_de_passe,
            "password_confirm": mot_de_passe,
            "nom_complet": "Client faible",
            "telephone": "620000009",
        },
        format="json",
    )
    assert reponse.status_code == 400
    corps = reponse.json()
    assert corps["success"] is False
    messages = corps["errors"]["password"]
    assert messages
    assert all("This password" not in m and "too " not in m for m in messages)
    from django.contrib.auth import get_user_model
    assert not get_user_model().objects.filter(email="faible@test.com").exists()


@pytest.mark.django_db
def test_inscription_accepte_mot_de_passe_solide(cache_vide):
    api = APIClient()
    reponse = api.post(
        "/api/public/auth/register/",
        {
            "email": "solide@test.com",
            "password": "Riviere-Soleil-42",
            "password_confirm": "Riviere-Soleil-42",
            "nom_complet": "Client solide",
            "telephone": "620000008",
        },
        format="json",
    )
    assert reponse.status_code == 201


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


@pytest.mark.django_db
@pytest.mark.parametrize("chemin", ["/api/v1/public/config-app/", "/api/public/config-app/"])
@override_settings(
    APP_CLIENT_VERSION_MIN="2.1.0",
    APP_CLIENT_VERSION_RECOMMANDEE="2.3.0",
    APP_EQUIPE_VERSION_MIN="1.4.0",
    APP_EQUIPE_VERSION_RECOMMANDEE="1.5.0",
    APP_MESSAGE_MISE_A_JOUR="Mettez l'application à jour.",
)
def test_config_app_accessible_sans_authentification_et_valeurs_configurables(chemin):
    reponse = APIClient().get(chemin)
    assert reponse.status_code == 200
    assert reponse.json() == {
        "success": True,
        "data": {
            "client": {"version_minimale": "2.1.0", "version_recommandee": "2.3.0"},
            "equipe": {"version_minimale": "1.4.0", "version_recommandee": "1.5.0"},
            "message_mise_a_jour": "Mettez l'application à jour.",
        },
        "message": "",
    }
