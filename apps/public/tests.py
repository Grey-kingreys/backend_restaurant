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
