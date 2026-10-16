"""Slug public stocké et unique d'un restaurant."""
import pytest
from rest_framework.test import APIClient

from apps.company.models import Restaurant


@pytest.mark.django_db
def test_slug_rempli_a_la_creation_comme_get_slug():
    resto = Restaurant.objects.create(nom="Le Baobab")
    assert resto.slug == resto.get_slug() == "lebaobab"


@pytest.mark.django_db
def test_noms_en_collision_obtiennent_des_slugs_distincts():
    a = Restaurant.objects.create(nom="Le Baobab")
    b = Restaurant.objects.create(nom="le  baobab!")
    c = Restaurant.objects.create(nom="LE-BAOBAB")
    assert [a.slug, b.slug, c.slug] == ["lebaobab", "lebaobab-2", "lebaobab-3"]


@pytest.mark.django_db
def test_slug_inchange_apres_renommage():
    resto = Restaurant.objects.create(nom="Le Baobab")
    resto.nom = "Chez Fatou"
    resto.save()
    resto.refresh_from_db()
    assert resto.slug == "lebaobab"
    assert resto.get_slug() == "chezfatou"


@pytest.mark.django_db
def test_nom_sans_caractere_exploitable():
    assert Restaurant.objects.create(nom="!!!").slug == "restaurant"


@pytest.mark.django_db
def test_repli_par_nom_et_slug_inconnu():
    from apps.public.api_views import get_restaurant_by_slug
    resto = Restaurant.objects.create(nom="Le Baobab")
    assert get_restaurant_by_slug("le-baobab") == resto
    assert get_restaurant_by_slug("lebaobab") == resto
    assert get_restaurant_by_slug("inconnu") is None


@pytest.mark.django_db
def test_resolution_par_slug_stocke():
    a = Restaurant.objects.create(nom="Le Baobab", accept_livraison=True)
    b = Restaurant.objects.create(nom="Le Baobab", accept_livraison=True)
    api = APIClient()
    assert api.get(f"/api/public/restaurants/{a.slug}/").json()["data"]["restaurant"]["id"] == a.id
    assert api.get(f"/api/public/restaurants/{b.slug}/").json()["data"]["restaurant"]["id"] == b.id
    assert api.get("/api/public/restaurants/inconnu/").status_code == 404
