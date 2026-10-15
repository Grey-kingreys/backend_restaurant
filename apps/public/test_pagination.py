"""Pagination optionnelle (?page=, ?taille=) des listes publiques."""
from datetime import date, time, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.commandes.models import Commande
from apps.menu.models import Plat
from apps.restaurant.models import Reservation, TableRestaurant

URLS = {
    "restaurants": "/api/public/restaurants/",
    "plats": "/api/public/plats/",
    "commandes": "/api/public/mes-commandes/",
    "reservations": "/api/public/mes-reservations/",
}


@pytest.fixture
def monde(user_factory, restaurant_factory):
    resto = restaurant_factory(nom="Le Baobab", accept_livraison=True, accept_emporter=True)
    compte_table = user_factory(login="table_01", email=None, role="Rtable", restaurant=resto)
    table = TableRestaurant.objects.create(
        restaurant=resto, numero_table="T1", nombre_places=4, utilisateur=compte_table,
    )
    client = user_factory(login="client_p", email="p@test.com", role="Rclient", restaurant=None)
    api = APIClient()
    api.force_authenticate(client)
    return api, resto, table, client


def _creer(resto, table, client, n):
    """Ajoute n restaurants, plats, commandes et réservations de plus."""
    from apps.company.models import Restaurant
    for i in range(n):
        Restaurant.objects.create(nom=f"Resto {i:03d}", accept_emporter=True)
        Plat.objects.create(restaurant=resto, nom=f"Plat {i:03d}", prix_unitaire=1000)
        Commande.objects.create(
            restaurant=resto, table=client, type_commande="emporter",
            montant_total=1000, statut="en_attente", cle_suivi=f"cle-{Commande.objects.count()}",
        )
        Reservation.objects.create(
            restaurant=resto, table=table, client=client,
            date_reservation=date.today() + timedelta(days=i + 1), heure=time(12, 0),
            nombre_personnes=2, duree_minutes=60, statut="en_attente",
        )


@pytest.mark.django_db
@pytest.mark.parametrize("nom", list(URLS))
def test_sans_page_forme_d_origine(monde, nom):
    api, resto, table, client = monde
    _creer(resto, table, client, 25)
    donnees = api.get(URLS[nom]).json()["data"]
    assert "resultats" not in donnees and "suivant" not in donnees
    cle_liste = {"restaurants": "restaurants", "plats": "plats",
                 "commandes": "commandes", "reservations": "reservations"}[nom]
    assert len(donnees[cle_liste]) >= 25  # liste complète, jamais tronquée


@pytest.mark.django_db
@pytest.mark.parametrize("nom", list(URLS))
def test_page_1_page_2_et_taille(monde, nom):
    api, resto, table, client = monde
    _creer(resto, table, client, 25)
    p1 = api.get(URLS[nom], {"page": 1}).json()["data"]
    attendues = {"count", "suivant", "precedent", "resultats"}
    assert set(p1) == (attendues | {"stats"} if nom == "commandes" else attendues)
    assert len(p1["resultats"]) == 20 and p1["precedent"] is None
    assert p1["suivant"].startswith("http://testserver" + URLS[nom]) and "page=2" in p1["suivant"]
    p2 = api.get(p1["suivant"]).json()["data"]
    assert len(p2["resultats"]) == p1["count"] - 20 and p2["suivant"] is None
    assert "page=1" in p2["precedent"]
    p5 = api.get(URLS[nom], {"page": 1, "taille": 5}).json()["data"]
    assert len(p5["resultats"]) == 5 and "taille=5" in p5["suivant"]


@pytest.mark.django_db
def test_mes_commandes_paginees_gardent_les_stats_globales(monde):
    api, resto, table, client = monde
    _creer(resto, table, client, 25)
    Commande.objects.filter(cle_suivi__in=["cle-0", "cle-1"]).update(statut="payee")
    Commande.objects.filter(cle_suivi="cle-2").update(statut="annulee")
    complet = api.get(URLS["commandes"]).json()["data"]
    page2 = api.get(URLS["commandes"], {"page": 2}).json()["data"]
    assert page2["stats"] == complet["stats"]
    assert complet["stats"] == {"total": 25, "en_cours": 22, "total_depense": "2000.00"}
    assert len(page2["resultats"]) == 5
    # Sans commande payée, même format qu'en forme d'origine
    Commande.objects.update(statut="en_attente")
    assert api.get(URLS["commandes"], {"page": 1}).json()["data"]["stats"] == \
        api.get(URLS["commandes"]).json()["data"]["stats"]


@pytest.mark.django_db
@pytest.mark.parametrize("nom", list(URLS))
def test_page_hors_limites_404(monde, nom):
    api, resto, table, client = monde
    _creer(resto, table, client, 3)
    reponse = api.get(URLS[nom], {"page": 99})
    assert reponse.status_code == 404
    assert reponse.json() == {"success": False, "message": "Cette page n'existe pas.", "errors": None}


@pytest.mark.django_db
@pytest.mark.parametrize("params,message", [
    ({"page": 0}, "Le numéro de page doit être un nombre entier supérieur ou égal à 1."),
    ({"page": -2}, "Le numéro de page doit être un nombre entier supérieur ou égal à 1."),
    ({"page": "abc"}, "Le numéro de page doit être un nombre entier supérieur ou égal à 1."),
    ({"page": ""}, "Le numéro de page doit être un nombre entier supérieur ou égal à 1."),
    ({"page": 1, "taille": 0}, "La taille de page doit être un nombre entier entre 1 et 50."),
    ({"page": 1, "taille": 51}, "La taille de page doit être un nombre entier entre 1 et 50."),
    ({"page": 1, "taille": "x"}, "La taille de page doit être un nombre entier entre 1 et 50."),
])
def test_parametres_invalides_400_en_francais(monde, params, message):
    api, *_ = monde
    reponse = api.get(URLS["restaurants"], params)
    assert reponse.status_code == 400
    assert reponse.json()["success"] is False and reponse.json()["message"] == message


@pytest.mark.django_db
def test_page_vide_valide_pour_une_liste_vide(monde):
    api, *_ = monde
    donnees = api.get(URLS["reservations"], {"page": 1}).json()["data"]
    assert donnees == {"count": 0, "suivant": None, "precedent": None, "resultats": []}


@pytest.mark.django_db
@pytest.mark.parametrize("nom", ["commandes", "reservations", "plats"])
def test_pas_de_requetes_supplementaires_par_element(monde, nom):
    api, resto, table, client = monde
    _creer(resto, table, client, 3)
    with CaptureQueriesContext(connection) as peu:
        api.get(URLS[nom], {"page": 1, "taille": 50})
    _creer(resto, table, client, 30)
    with CaptureQueriesContext(connection) as beaucoup:
        api.get(URLS[nom], {"page": 1, "taille": 50})
    assert len(beaucoup) == len(peu)
