"""Période de grâce de 60 s du rafraîchissement de connexion."""
import threading

import pytest
from django.core.cache import cache
from django.db import connection
from rest_framework.test import APIClient

from apps.accounts.models import User

URL = "/api/accounts/auth/token/refresh/"
URL_V1 = "/api/v1/accounts/auth/token/refresh/"


@pytest.fixture(autouse=True)
def cache_vide():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def connexion(restaurant_factory):
    User.objects.create_user(
        login="serveur", email="serveur@test.com", password="correctpass",
        role="Rserveur", restaurant=restaurant_factory(),
    )
    api = APIClient()
    res = api.post(
        "/api/accounts/auth/login/",
        {"email": "serveur@test.com", "password": "correctpass"}, format="json",
    )
    return api, res.data["data"]


@pytest.mark.django_db
def test_meme_refresh_rejoue_donne_le_meme_couple(connexion):
    api, jetons = connexion
    premier = api.post(URL, {"refresh": jetons["refresh"]}, format="json")
    second = api.post(URL_V1, {"refresh": jetons["refresh"]}, format="json")
    assert premier.status_code == second.status_code == 200
    assert set(premier.json()) == {"access", "refresh"}
    assert second.json() == premier.json()
    assert premier.json()["refresh"] != jetons["refresh"]


@pytest.mark.django_db
def test_apres_la_fenetre_le_refresh_rejoue_est_refuse(connexion):
    api, jetons = connexion
    assert api.post(URL, {"refresh": jetons["refresh"]}, format="json").status_code == 200
    cache.clear()  # équivaut à l'écoulement des 60 s
    assert api.post(URL, {"refresh": jetons["refresh"]}, format="json").status_code == 401


@pytest.mark.django_db
def test_refresh_deconnecte_reste_refuse_meme_dans_la_fenetre(connexion):
    api, jetons = connexion
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {jetons['access']}")
    nouveau = api.post(URL, {"refresh": jetons["refresh"]}, format="json").json()
    # Déconnexion avec le refresh d'origine (déjà tourné, donc 400) puis rejeu dans la fenêtre
    assert api.post("/api/accounts/auth/logout/", {"refresh": jetons["refresh"]}, format="json").status_code == 400
    assert api.post(URL, {"refresh": jetons["refresh"]}, format="json").status_code == 401
    # Déconnexion avec le nouveau refresh : l'ancien ne ressuscite pas non plus
    cache.clear()
    jetons2 = nouveau
    nouveau2 = api.post(URL, {"refresh": jetons2["refresh"]}, format="json").json()
    assert api.post("/api/accounts/auth/logout/", {"refresh": nouveau2["refresh"]}, format="json").status_code == 200
    assert api.post(URL, {"refresh": jetons2["refresh"]}, format="json").status_code == 401
    assert api.post(URL, {"refresh": nouveau2["refresh"]}, format="json").status_code == 401


@pytest.mark.django_db
def test_couple_memorise_pendant_la_prise_du_verrou(connexion, monkeypatch):
    """Course : le couple apparaît entre la première lecture et la prise du verrou."""
    from apps.accounts import refresh_grace
    api, jetons = connexion
    premier = api.post(URL, {"refresh": jetons["refresh"]}, format="json").json()
    lire_reel = refresh_grace.lire
    appels = {"n": 0}

    def lire_course(jti):
        # La première lecture ne voit rien ; la relecture après le verrou voit le couple
        appels["n"] += 1
        return None if appels["n"] == 1 else lire_reel(jti)

    monkeypatch.setattr(refresh_grace, "lire", lire_course)
    reponse = api.post(URL, {"refresh": jetons["refresh"]}, format="json")
    assert reponse.status_code == 200
    assert reponse.json() == premier
    assert appels["n"] == 2


@pytest.mark.django_db
def test_refresh_invalide_donne_401(connexion):
    api, _ = connexion
    assert api.post(URL, {"refresh": "pas-un-jeton"}, format="json").status_code == 401
    assert api.post(URL, {}, format="json").status_code == 400


@pytest.mark.django_db(transaction=True)
def test_deux_refresh_simultanes_donnent_le_meme_couple(connexion):
    _, jetons = connexion
    resultats = []

    def appel():
        reponse = APIClient().post(URL, {"refresh": jetons["refresh"]}, format="json")
        resultats.append((reponse.status_code, reponse.json()))
        connection.close()

    fils = [threading.Thread(target=appel) for _ in range(4)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    assert [s for s, _ in resultats] == [200] * 4
    assert all(corps == resultats[0][1] for _, corps in resultats)
