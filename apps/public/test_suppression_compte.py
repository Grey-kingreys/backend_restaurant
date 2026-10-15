"""Suppression de compte client par anonymisation (D09)."""
from datetime import date, timedelta
from unittest import mock

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.accounts.models import AdresseClient, User
from apps.commandes.models import Commande
from apps.commandes.serializers import CommandeDetailSerializer, CommandeListSerializer
from apps.commandes.pdf_utils import _client_display
from apps.menu.models import Plat
from apps.paiements.models import Paiement
from apps.public.models import CleIdempotence
from apps.restaurant.models import Reservation, TableRestaurant

URL = "/api/v1/public/mon-compte/supprimer/"
URL_REFRESH = "/api/accounts/auth/token/refresh/"
MOT_DE_PASSE = "motdepasse123"


@pytest.fixture
def client_inscrit(restaurant_factory, user_factory):
    cache.clear()  # compteur de limitation de l'inscription
    resto = restaurant_factory(nom="Le Baobab", accept_livraison=True, accept_emporter=True)
    plat = Plat.objects.create(restaurant=resto, nom="Poulet", prix_unitaire=50000)
    compte_table = user_factory(login="table_01", email=None, role="Rtable", restaurant=resto)
    TableRestaurant.objects.create(
        restaurant=resto, numero_table="T1", nombre_places=4, utilisateur=compte_table,
    )
    api = APIClient()
    inscription = api.post(
        "/api/public/auth/register/",
        {"email": "awa@test.com", "password": MOT_DE_PASSE, "password_confirm": MOT_DE_PASSE,
         "nom_complet": "Awa Diallo", "telephone": "620000001"},
        format="json",
    )
    assert inscription.status_code == 201
    jetons = inscription.data["data"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {jetons['access']}")
    return api, jetons, resto, plat, User.objects.get(email="awa@test.com")


def _commander(api, resto, plat, cle="cle-awa"):
    return api.post(
        f"/api/public/restaurants/{resto.slug}/commander/",
        {"type_commande": "livraison", "mode_paiement": "livraison", "telephone": "620000001",
         "adresse_livraison": "Face à la pharmacie, portail bleu", "latitude": "9.5", "longitude": "-13.7",
         "items": [{"plat_id": plat.id, "quantite": 1}]},
        format="json", HTTP_IDEMPOTENCY_KEY=cle,
    )


@pytest.mark.django_db
def test_suppression_complete(client_inscrit):
    api, jetons, resto, plat, user = client_inscrit
    assert _commander(api, resto, plat).status_code == 201
    commande = Commande.objects.get()
    Paiement.objects.create(commande=commande, montant=50000)
    Commande.objects.filter(pk=commande.pk).update(statut="payee")  # terminée : suppression permise
    AdresseClient.objects.create(user=user, libelle="Maison", description="Près du marché")
    demain = (date.today() + timedelta(days=1)).isoformat()
    resa = api.post(
        f"/api/public/restaurants/{resto.slug}/reserver/",
        {"date": demain, "heure": "12:00", "note": "Allergie arachide"}, format="json",
    )
    assert resa.status_code == 201

    reponse = api.post(URL, {"password": MOT_DE_PASSE}, format="json")
    assert reponse.status_code == 200

    user.refresh_from_db()
    assert user.actif is False and user.telephone is None
    assert user.nom_complet == "Client supprimé"
    assert "awa" not in user.email and "awa" not in user.login
    assert not AdresseClient.objects.filter(user=user).exists()
    assert not CleIdempotence.objects.filter(utilisateur=user).exists()

    # Commande et paiement conservés, sans données personnelles
    commande.refresh_from_db()
    assert Commande.objects.count() == 1 and Paiement.objects.count() == 1
    assert commande.client_nom is None and commande.client_telephone is None
    assert commande.client_adresse_livraison is None
    assert commande.client_latitude is None and commande.client_longitude is None

    # Réservation à venir annulée, note effacée
    reservation = Reservation.objects.get()
    assert reservation.statut == "annulee" and reservation.note == ""

    # Affichage staff et PDF sans erreur
    assert CommandeListSerializer(commande).data["client_display"] == "Client supprimé"
    assert CommandeDetailSerializer(commande).data["client_nom"] is None
    assert _client_display(commande) == "Client supprimé"


@pytest.mark.django_db
def test_connexion_impossible_et_email_reutilisable(client_inscrit):
    api, _, _, _, _ = client_inscrit
    assert api.post(URL, {"password": MOT_DE_PASSE}, format="json").status_code == 200
    connexion = APIClient().post(
        "/api/accounts/auth/login/", {"email": "awa@test.com", "password": MOT_DE_PASSE}, format="json",
    )
    assert connexion.status_code == 400
    nouvelle = APIClient().post(
        "/api/public/auth/register/",
        {"email": "awa@test.com", "password": MOT_DE_PASSE, "password_confirm": MOT_DE_PASSE,
         "nom_complet": "Awa Nouvelle", "telephone": "620000002"},
        format="json",
    )
    assert nouvelle.status_code == 201


@pytest.mark.django_db
def test_refresh_refuse_apres_suppression_meme_pendant_la_grace(client_inscrit):
    api, jetons, _, _, user = client_inscrit
    # Rotation : le couple est mémorisé 60 s (période de grâce)
    assert APIClient().post(URL_REFRESH, {"refresh": jetons["refresh"]}, format="json").status_code == 200
    assert api.post(URL, {"password": MOT_DE_PASSE}, format="json").status_code == 200
    assert APIClient().post(URL_REFRESH, {"refresh": jetons["refresh"]}, format="json").status_code == 401
    assert BlacklistedToken.objects.filter(token__user=user).count() == OutstandingToken.objects.filter(user=user).count()


@pytest.mark.django_db
def test_mauvais_mot_de_passe_et_compte_staff(client_inscrit, user_factory):
    api, _, _, _, user = client_inscrit
    assert api.post(URL, {"password": "mauvais"}, format="json").status_code == 400
    assert api.post(URL, {}, format="json").status_code == 400
    user.refresh_from_db()
    assert user.actif is True and user.nom_complet == "Awa Diallo"

    staff = user_factory(login="serveur", email="serveur@test.com", role="Rserveur")
    autre = APIClient()
    autre.force_authenticate(staff)
    assert autre.post(URL, {"password": "testpass123"}, format="json").status_code == 403


@pytest.mark.django_db
def test_echec_au_milieu_ne_laisse_rien_a_moitie(client_inscrit):
    api, _, resto, plat, user = client_inscrit
    _commander(api, resto, plat)
    Commande.objects.update(statut="servie")  # terminée : la suppression est permise
    AdresseClient.objects.create(user=user, libelle="Maison", description="Près du marché")
    with mock.patch("apps.public.api_views.CleIdempotence.objects.filter", side_effect=RuntimeError("panne")):
        api.raise_request_exception = False
        reponse = api.post(URL, {"password": MOT_DE_PASSE}, format="json")
    assert reponse.status_code == 500
    user.refresh_from_db()
    commande = Commande.objects.get()
    assert user.actif is True and user.nom_complet == "Awa Diallo"
    assert commande.client_nom == "Awa Diallo" and commande.client_telephone == "620000001"
    assert AdresseClient.objects.filter(user=user).exists()
    assert not BlacklistedToken.objects.filter(token__user=user).exists()


@pytest.mark.django_db
def test_motif_d_annulation_du_client_efface_mais_pas_celui_du_personnel(client_inscrit, user_factory):
    api, _, resto, plat, user = client_inscrit
    _commander(api, resto, plat)
    commande = Commande.objects.get()
    annulation = api.post(
        f"/api/public/mes-commandes/{commande.id}/annuler/",
        {"motif": "Je suis chez Mme Awa Diallo, tel 620000001"}, format="json",
    )
    assert annulation.status_code == 200
    # Autre commande annulée par le personnel, avec son propre motif
    assert _commander(api, resto, plat, cle="cle-awa-2").status_code == 201
    staff = user_factory(login="serveur", email="serveur@test.com", role="Rserveur", restaurant=resto)
    seconde = Commande.objects.exclude(pk=commande.pk).get()
    seconde.annuler(par=staff, motif="Plat épuisé")

    assert api.post(URL, {"password": MOT_DE_PASSE}, format="json").status_code == 200
    commande.refresh_from_db()
    seconde.refresh_from_db()
    assert commande.statut == "annulee" and commande.motif_annulation is None
    assert seconde.motif_annulation == "Plat épuisé"


@pytest.mark.django_db
def test_affichages_staff_d_un_compte_supprime(client_inscrit):
    from apps.paiements.serializers import PaiementSerializer
    from apps.restaurant.api_views import _serialize_resa_staff
    api, _, resto, plat, user = client_inscrit
    _commander(api, resto, plat)
    commande = Commande.objects.get()
    paiement = Paiement.objects.create(commande=commande, montant=50000)
    demain = (date.today() + timedelta(days=1)).isoformat()
    api.post(f"/api/public/restaurants/{resto.slug}/reserver/", {"date": demain, "heure": "12:00"}, format="json")
    Commande.objects.update(statut="payee")
    assert api.post(URL, {"password": MOT_DE_PASSE}, format="json").status_code == 200
    user.refresh_from_db()
    assert user.est_supprime and user.login_affiche == "Client supprimé"
    # Un client actif inscrit avec ce domaine n'est pas pris pour un compte supprimé
    imposteur = User(login="imposteur", role="Rclient", email="x@compte-supprime.invalid", is_active=True)
    assert not imposteur.est_supprime and imposteur.login_affiche == "imposteur"
    assert "supprime_" not in str(PaiementSerializer(paiement).data["commande_table_login"])
    resa = _serialize_resa_staff(Reservation.objects.select_related("client", "table").get())
    assert resa["client_email"] is None and resa["client_nom"] == "Client supprimé"


@pytest.mark.django_db
def test_table_login_serializers_commandes(client_inscrit):
    api, _, resto, plat, user = client_inscrit
    _commander(api, resto, plat)
    commande = Commande.objects.get()
    table = commande.restaurant.users.get(role="Rtable")
    sur_table = Commande.objects.create(restaurant=resto, table=table, montant_total=1000)
    Commande.objects.update(statut="payee")
    assert api.post(URL, {"password": MOT_DE_PASSE}, format="json").status_code == 200
    commande.refresh_from_db()
    assert CommandeListSerializer(commande).data["table_login"] == "Client supprimé"
    assert CommandeDetailSerializer(commande).data["table_login"] == "Client supprimé"
    # Une table garde son login réel
    assert CommandeListSerializer(sur_table).data["table_login"] == "table_01"


@pytest.mark.django_db
def test_suppression_limitee_a_5_essais_par_heure(client_inscrit):
    api, _, _, _, _ = client_inscrit
    for _ in range(5):
        assert api.post(URL, {"password": "mauvais"}, format="json").status_code == 400
    reponse = api.post(URL, {"password": "mauvais"}, format="json")
    assert reponse.status_code == 429
    assert reponse.json()["success"] is False


@pytest.mark.django_db
@pytest.mark.parametrize("statut", ["en_attente", "prete", "en_livraison"])
def test_suppression_refusee_avec_commande_en_cours(client_inscrit, statut):
    api, _, resto, plat, user = client_inscrit
    _commander(api, resto, plat)
    Commande.objects.update(statut=statut)
    reponse = api.post(URL, {"password": MOT_DE_PASSE}, format="json")
    assert reponse.status_code == 409
    assert reponse.json()["success"] is False
    assert reponse.json()["message"] == (
        "Vous avez une commande en cours. Vous pourrez supprimer votre compte une fois qu'elle sera terminée."
    )
    user.refresh_from_db()
    commande = Commande.objects.get()
    assert user.actif is True and user.nom_complet == "Awa Diallo"
    assert commande.client_nom == "Awa Diallo" and commande.client_adresse_livraison
    assert not BlacklistedToken.objects.filter(token__user=user).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("statut", ["servie", "payee", "annulee"])
def test_suppression_permise_avec_commande_terminee(client_inscrit, statut):
    api, _, resto, plat, _ = client_inscrit
    _commander(api, resto, plat)
    Commande.objects.update(statut=statut)
    assert api.post(URL, {"password": MOT_DE_PASSE}, format="json").status_code == 200


@pytest.mark.django_db
def test_suppression_refusee_avec_reservation_confirmee_aujourdhui(client_inscrit):
    api, _, resto, _, user = client_inscrit
    table = TableRestaurant.objects.get()
    Reservation.objects.create(
        restaurant=resto, table=table, client=user, date_reservation=date.today(),
        heure="23:00", nombre_personnes=2, duree_minutes=60, statut="confirmee",
    )
    reponse = api.post(URL, {"password": MOT_DE_PASSE}, format="json")
    assert reponse.status_code == 409
    assert "réservation confirmée aujourd'hui" in reponse.json()["message"]
    user.refresh_from_db()
    assert user.actif is True
