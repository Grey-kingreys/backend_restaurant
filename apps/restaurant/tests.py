"""Tests de l'app restaurant."""
from decimal import Decimal

import pytest

from apps.commandes.models import Commande
from apps.menu.models import Plat
from apps.restaurant.models import TableRestaurant, TableSession


def _table_avec_session(user_factory, restaurant_factory, **resto_kwargs):
    """Table Rtable rattachee a une session QR active. Retourne (table, session)."""
    resto = restaurant_factory(nom="Resto GPS", **resto_kwargs)
    compte = user_factory(login="tab_gps", email=None, role="Rtable", restaurant=resto)
    TableRestaurant.objects.create(
        restaurant=resto, numero_table="G1", nombre_places=2, utilisateur=compte,
    )
    session = TableSession.ouvrir_pour(compte, django_session_key="cle-test-gps")
    return compte, session


@pytest.mark.django_db
class TestCheckPosition:
    """
    Verification GPS periodique d'une session table.

    Regression : la vue filtrait les commandes sur `Commande.user`, champ qui
    n'existe pas (c'est `table`). Django levait FieldError -> HTTP 500 a chaque
    appel des qu'une session etait active, rendant la verification GPS
    totalement inoperante en production.
    """

    URL = "/api/restaurant/tables/check-position/"

    def test_session_active_sans_commande_ne_leve_pas_derreur(
        self, api_client, user_factory, restaurant_factory
    ):
        compte, _ = _table_avec_session(user_factory, restaurant_factory)
        api_client._authenticate(compte)

        res = api_client.post(self.URL, {}, format="json")

        assert res.status_code == 200
        assert res.data["data"]["status"] == "ok"

    def test_commande_active_de_la_session_empeche_la_deconnexion(
        self, api_client, user_factory, restaurant_factory
    ):
        compte, session = _table_avec_session(user_factory, restaurant_factory)
        plat = Plat.objects.create(
            restaurant=compte.restaurant, nom="Riz", prix_unitaire=Decimal("25000"),
            categorie="PLAT", disponible=True,
        )
        commande = Commande.objects.create(
            restaurant=compte.restaurant, table=compte, session=session,
            montant_total=plat.prix_unitaire, statut="en_attente",
        )
        api_client._authenticate(compte)

        res = api_client.post(self.URL, {}, format="json")

        assert res.status_code == 200
        # Une commande en cours : la table reste active, pas de compte a rebours.
        assert res.data["data"]["status"] == "ok"
        assert commande.statut == "en_attente"

    def test_commandes_toutes_payees_declenche_le_compte_a_rebours(
        self, api_client, user_factory, restaurant_factory
    ):
        compte, session = _table_avec_session(user_factory, restaurant_factory)
        Commande.objects.create(
            restaurant=compte.restaurant, table=compte, session=session,
            montant_total=Decimal("25000"), statut="payee",
        )
        api_client._authenticate(compte)

        res = api_client.post(self.URL, {}, format="json")

        assert res.status_code == 200
        assert res.data["data"]["status"] == "all_paid"
        assert res.data["data"]["paid_at"]

    def test_commande_dune_session_precedente_ignoree(
        self, api_client, user_factory, restaurant_factory
    ):
        """
        Une commande payee lors d'une session anterieure ne doit pas faire croire
        que la nouvelle session est terminee - sinon la table serait deconnectee
        des sa connexion.
        """
        compte, ancienne = _table_avec_session(user_factory, restaurant_factory)
        Commande.objects.create(
            restaurant=compte.restaurant, table=compte, session=ancienne,
            montant_total=Decimal("25000"), statut="payee",
        )
        # Nouveau scan QR : l'ancienne session est desactivee, une neuve s'ouvre.
        TableSession.ouvrir_pour(compte, django_session_key="cle-test-gps-2")
        api_client._authenticate(compte)

        res = api_client.post(self.URL, {}, format="json")

        assert res.status_code == 200
        assert res.data["data"]["status"] == "ok"

    def test_hors_zone_incremente_les_avertissements(
        self, api_client, user_factory, restaurant_factory
    ):
        compte, session = _table_avec_session(
            user_factory, restaurant_factory,
            latitude=Decimal("9.641185"), longitude=Decimal("-13.578401"),
            rayon_connexion=200,
        )
        api_client._authenticate(compte)

        # Coordonnees volontairement tres eloignees du restaurant.
        res = api_client.post(self.URL, {"lat": 48.8566, "lng": 2.3522}, format="json")

        assert res.status_code == 200
        assert res.data["data"]["status"] == "out_of_range"
        assert res.data["data"]["strikes"] == 1
        assert res.data["data"]["disconnect"] is False

    def test_reserve_aux_tables(self, api_client, user_factory, restaurant_factory):
        serveur = user_factory(login="srv_gps", email="srv_gps@t.com", role="Rserveur")
        api_client._authenticate(serveur)

        res = api_client.post(self.URL, {}, format="json")

        assert res.status_code == 403
