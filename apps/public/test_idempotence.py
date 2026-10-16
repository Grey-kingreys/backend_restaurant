"""Idempotence de commander et réserver (en-tête Idempotency-Key)."""
import threading
from datetime import date, timedelta

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.commandes.models import Commande
from apps.menu.models import Plat
from apps.public.models import CleIdempotence
from apps.public.tasks import purger_cles_idempotence
from apps.restaurant.models import Reservation, TableRestaurant


@pytest.fixture
def monde(user_factory, restaurant_factory):
    resto = restaurant_factory(nom="Le Baobab", accept_livraison=True, accept_emporter=True)
    plat = Plat.objects.create(restaurant=resto, nom="Poulet braisé", prix_unitaire=50000)
    compte_table = user_factory(login="table_01", email=None, role="Rtable", restaurant=resto)
    TableRestaurant.objects.create(
        restaurant=resto, numero_table="T1", nombre_places=4, utilisateur=compte_table,
    )
    client_a = user_factory(login="client_a", email="a@test.com", role="Rclient", restaurant=None)
    client_b = user_factory(login="client_b", email="b@test.com", role="Rclient", restaurant=None)
    return resto, plat, client_a, client_b


def _api(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


def _corps_commande(plat, quantite=1):
    return {
        "type_commande": "emporter", "mode_paiement": "livraison",
        "telephone": "620000000", "items": [{"plat_id": plat.id, "quantite": quantite}],
    }


def _url_commander(resto, prefixe="/api"):
    return f"{prefixe}/public/restaurants/{resto.slug}/commander/"


@pytest.mark.django_db
def test_commander_meme_cle_meme_corps_une_seule_commande(monde):
    resto, plat, client_a, _ = monde
    api = _api(client_a)
    entetes = {"HTTP_IDEMPOTENCY_KEY": "cmd-1"}
    premiere = api.post(_url_commander(resto), _corps_commande(plat), format="json", **entetes)
    seconde = api.post(_url_commander(resto), _corps_commande(plat), format="json", **entetes)
    assert premiere.status_code == seconde.status_code == 201
    assert seconde.json() == premiere.json()
    assert Commande.objects.count() == 1


@pytest.mark.django_db
def test_commander_meme_cle_corps_different_donne_409(monde):
    resto, plat, client_a, _ = monde
    api = _api(client_a)
    entetes = {"HTTP_IDEMPOTENCY_KEY": "cmd-2"}
    api.post(_url_commander(resto), _corps_commande(plat, 1), format="json", **entetes)
    reponse = api.post(_url_commander(resto), _corps_commande(plat, 2), format="json", **entetes)
    assert reponse.status_code == 409
    assert reponse.json()["success"] is False
    assert reponse.json()["message"] == "Cette demande a déjà été envoyée avec d'autres informations."
    assert Commande.objects.count() == 1


@pytest.mark.django_db
def test_commander_sans_cle_cree_deux_commandes(monde):
    resto, plat, client_a, _ = monde
    api = _api(client_a)
    assert api.post(_url_commander(resto), _corps_commande(plat), format="json").status_code == 201
    assert api.post(_url_commander(resto), _corps_commande(plat), format="json").status_code == 201
    assert Commande.objects.count() == 2
    assert not CleIdempotence.objects.exists()


@pytest.mark.django_db
def test_cle_isolee_par_utilisateur_et_par_route(monde):
    resto, plat, client_a, client_b = monde
    entetes = {"HTTP_IDEMPOTENCY_KEY": "partagee"}
    corps = _corps_commande(plat)
    assert _api(client_a).post(_url_commander(resto), corps, format="json", **entetes).status_code == 201
    # Autre client, même clé, même corps : nouvelle commande, pas de rejeu
    assert _api(client_b).post(_url_commander(resto), corps, format="json", **entetes).status_code == 201
    # Autre route (alias v1), même client et même clé : pas de rejeu non plus
    assert _api(client_a).post(_url_commander(resto, "/api/v1"), corps, format="json", **entetes).status_code == 201
    assert Commande.objects.count() == 3


@pytest.mark.django_db
def test_erreur_non_memorisee_puis_nouvel_essai_possible(monde):
    resto, plat, client_a, _ = monde
    api = _api(client_a)
    entetes = {"HTTP_IDEMPOTENCY_KEY": "cmd-erreur"}
    plat.disponible = False
    plat.save()
    assert api.post(_url_commander(resto), _corps_commande(plat), format="json", **entetes).status_code == 400
    assert not CleIdempotence.objects.exists()
    plat.disponible = True
    plat.save()
    # Même clé, même corps, état corrigé : la commande est bien créée
    assert api.post(_url_commander(resto), _corps_commande(plat), format="json", **entetes).status_code == 201
    assert Commande.objects.count() == 1


@pytest.mark.django_db
def test_reserver_meme_cle_une_seule_reservation_et_409_si_corps_different(monde):
    resto, _, client_a, _ = monde
    api = _api(client_a)
    url = f"/api/public/restaurants/{resto.slug}/reserver/"
    demain = (date.today() + timedelta(days=1)).isoformat()
    corps = {"date": demain, "heure": "12:00", "nombre_personnes": 2}
    entetes = {"HTTP_IDEMPOTENCY_KEY": "resa-1"}
    premiere = api.post(url, corps, format="json", **entetes)
    seconde = api.post(url, corps, format="json", **entetes)
    assert premiere.status_code == seconde.status_code == 201
    assert seconde.json() == premiere.json()
    assert Reservation.objects.count() == 1
    autre = api.post(url, {**corps, "nombre_personnes": 3}, format="json", **entetes)
    assert autre.status_code == 409
    assert Reservation.objects.count() == 1


@pytest.mark.django_db
def test_reserver_sans_cle_deux_reservations(monde):
    resto, _, client_a, _ = monde
    api = _api(client_a)
    url = f"/api/public/restaurants/{resto.slug}/reserver/"
    # Deux créneaux éloignés pour que la seule table reste libre
    demain = (date.today() + timedelta(days=1)).isoformat()
    assert api.post(url, {"date": demain, "heure": "12:00"}, format="json").status_code == 201
    assert api.post(url, {"date": demain, "heure": "20:00"}, format="json").status_code == 201
    assert Reservation.objects.count() == 2


@pytest.mark.django_db
def test_purge_des_cles_de_plus_de_24_heures(monde):
    _, _, client_a, _ = monde
    ancienne = CleIdempotence.objects.create(cle="vieille", utilisateur=client_a, route="POST /x", empreinte="0" * 64)
    recente = CleIdempotence.objects.create(cle="neuve", utilisateur=client_a, route="POST /x", empreinte="0" * 64)
    CleIdempotence.objects.filter(pk=ancienne.pk).update(date_creation=timezone.now() - timedelta(hours=25))
    assert purger_cles_idempotence() == 1
    assert list(CleIdempotence.objects.all()) == [recente]


def test_purge_planifiee_dans_beat():
    from backend.celery import app
    entree = app.conf.beat_schedule["purger-cles-idempotence"]
    assert entree["task"] == "apps.public.tasks.purger_cles_idempotence"


@pytest.mark.django_db(transaction=True)
def test_requetes_simultanees_meme_cle_une_seule_commande(monde):
    resto, plat, client_a, _ = monde
    resultats = []

    def appel():
        reponse = _api(client_a).post(
            _url_commander(resto), _corps_commande(plat), format="json",
            HTTP_IDEMPOTENCY_KEY="cmd-course",
        )
        resultats.append((reponse.status_code, reponse.json()))
        connection.close()

    fils = [threading.Thread(target=appel) for _ in range(6)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    assert [s for s, _ in resultats] == [201] * 6
    assert all(corps == resultats[0][1] for _, corps in resultats)
    assert Commande.objects.count() == 1
