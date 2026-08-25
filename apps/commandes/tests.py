"""Tests app commandes — sessions de table, mes-commandes & prise de commande staff."""
from decimal import Decimal

import pytest
from apps.menu.models import Plat
from apps.restaurant.models import TableRestaurant, TableSession


def _table(user_factory, restaurant_factory, login="tab_regr"):
    r = restaurant_factory()
    return user_factory(login=login, email=None, role="Rtable", restaurant=r)


def _session(table, key, active=True):
    return TableSession.objects.create(
        table=table, django_session_key=key, est_active=active
    )


@pytest.mark.django_db
class TestMesCommandesSessions:
    """/api/commandes/mes-commandes/ face aux sessions actives multiples."""

    def test_mes_commandes_ok_avec_plusieurs_sessions_actives(
        self, api_client, user_factory, restaurant_factory
    ):
        """Régression : plusieurs sessions actives → 200, pas 500.

        Avant, _session_active() faisait .get(est_active=True) et levait
        MultipleObjectsReturned (non rattrapé) → 500 → « Impossible de
        charger vos commandes » côté front.
        """
        table = _table(user_factory, restaurant_factory)
        _session(table, "sess-a")
        _session(table, "sess-b")
        _session(table, "sess-c")

        api_client._authenticate(table)
        res = api_client.get("/api/commandes/mes-commandes/")

        assert res.status_code == 200
        assert res.data["success"] is True
        assert "commandes" in res.data["data"]

    def test_mes_commandes_refuse_non_table(
        self, api_client, user_factory, restaurant_factory
    ):
        """Un rôle non-Table reçoit 403."""
        r = restaurant_factory()
        serveur = user_factory(login="srv_regr", email="srv@t.com",
                               role="Rserveur", restaurant=r)
        api_client._authenticate(serveur)
        assert api_client.get("/api/commandes/mes-commandes/").status_code == 403


@pytest.mark.django_db
class TestTableSessionUnicite:
    """Une seule session active par table."""

    def test_ouvrir_pour_desactive_les_precedentes(
        self, user_factory, restaurant_factory
    ):
        table = _table(user_factory, restaurant_factory)
        _session(table, "old-1")
        _session(table, "old-2")

        nouvelle = TableSession.ouvrir_pour(table, django_session_key="new")

        actives = TableSession.objects.filter(table=table, est_active=True)
        assert actives.count() == 1
        assert actives.first().id == nouvelle.id

    def test_nettoyer_sessions_actives_multiples(
        self, user_factory, restaurant_factory
    ):
        table = _table(user_factory, restaurant_factory)
        _session(table, "s1")
        _session(table, "s2")
        derniere = _session(table, "s3")

        desactivees = TableSession.nettoyer_sessions_actives_multiples()

        assert desactivees == 2
        actives = TableSession.objects.filter(table=table, est_active=True)
        assert list(actives.values_list("id", flat=True)) == [derniere.id]


# ─────────────────────────────────────────────────────────────────────────────
# PRISE DE COMMANDE STAFF — /api/commandes/creer/ (sur_table / livraison / emporter)
# ─────────────────────────────────────────────────────────────────────────────

def _staff_setup(user_factory, restaurant_factory, frais_livraison=None):
    """Restaurant + serveur + table (avec compte) + plat. Retourne (serveur, table_resto, plat)."""
    from apps.accounts.serializers import get_role_config_for_role

    r = restaurant_factory(nom="Resto Staff", frais_livraison=frais_livraison)
    serveur = user_factory(login="srv_staff", email="srv_staff@t.com",
                           role="Rserveur", restaurant=r)
    # Sans role_config, has_permission() renvoie False (RBAC) → 403
    serveur.role_config = get_role_config_for_role(serveur.role)
    serveur.save(update_fields=["role_config"])
    compte_table = user_factory(login="tab_staff", email=None,
                                role="Rtable", restaurant=r)
    table_resto = TableRestaurant.objects.create(
        restaurant=r, numero_table="T1", nombre_places=4, utilisateur=compte_table,
    )
    plat = Plat.objects.create(
        restaurant=r, nom="Riz gras", prix_unitaire=Decimal("50000"),
        categorie="PLAT", disponible=True,
    )
    return serveur, table_resto, plat


@pytest.mark.django_db
class TestCommandeServeurCreer:
    """Le staff prend une commande sur table, en livraison ou à emporter."""

    def test_sur_table_non_regression(self, api_client, user_factory, restaurant_factory):
        serveur, table_resto, plat = _staff_setup(user_factory, restaurant_factory)
        api_client._authenticate(serveur)

        res = api_client.post("/api/commandes/creer/", {
            "table_id": table_resto.id,
            "items": [{"plat_id": plat.id, "quantite": 2}],
        }, format="json")

        assert res.status_code == 201
        data = res.data["data"]
        assert data["type_commande"] == "sur_table"
        assert data["table"] == table_resto.utilisateur_id
        assert Decimal(data["montant_total"]) == Decimal("100000")

    def test_livraison_client_de_passage(self, api_client, user_factory, restaurant_factory):
        serveur, _, plat = _staff_setup(
            user_factory, restaurant_factory, frais_livraison=Decimal("15000"),
        )
        api_client._authenticate(serveur)

        res = api_client.post("/api/commandes/creer/", {
            "type_commande": "livraison",
            "client_nom": "Mamadou Diallo",
            "client_telephone": "+224620000001",
            "client_adresse_livraison": "Quartier Kipé, Conakry",
            "items": [{"plat_id": plat.id, "quantite": 1}],
        }, format="json")

        assert res.status_code == 201
        data = res.data["data"]
        assert data["type_commande"] == "livraison"
        assert data["table"] is None
        assert data["table_login"] is None
        assert data["client_telephone"] == "+224620000001"
        assert data["client_adresse_livraison"] == "Quartier Kipé, Conakry"
        assert data["client_display"] == "Mamadou Diallo"
        # Pas de géolocalisation : adresse en texte libre uniquement
        assert data["client_latitude"] is None
        assert data["client_longitude"] is None
        # Le total ne couvre QUE les plats : les frais de livraison varient avec
        # la distance et se conviennent directement avec le livreur.
        assert Decimal(data["montant_total"]) == Decimal("50000")

        # Clé de suivi générée → lien/QR reçu possible, comme une commande en ligne
        from .models import Commande
        commande = Commande.objects.get(pk=data["id"])
        assert commande.cle_suivi
        assert str(commande)  # __str__ ne plante pas sans table

    def test_livraison_visible_dans_la_liste_livraisons(
        self, api_client, user_factory, restaurant_factory
    ):
        serveur, _, plat = _staff_setup(user_factory, restaurant_factory)
        api_client._authenticate(serveur)
        api_client.post("/api/commandes/creer/", {
            "type_commande": "livraison",
            "client_telephone": "+224620000002",
            "client_adresse_livraison": "Ratoma, Conakry",
            "items": [{"plat_id": plat.id, "quantite": 1}],
        }, format="json")

        res = api_client.get("/api/commandes/livraisons/")

        assert res.status_code == 200
        assert res.data["data"]["count"] == 1

    def test_emporter_sans_adresse(self, api_client, user_factory, restaurant_factory):
        serveur, _, plat = _staff_setup(user_factory, restaurant_factory)
        api_client._authenticate(serveur)

        res = api_client.post("/api/commandes/creer/", {
            "type_commande": "emporter",
            "client_nom": "Fatou",
            "items": [{"plat_id": plat.id, "quantite": 1}],
        }, format="json")

        assert res.status_code == 201
        data = res.data["data"]
        assert data["type_commande"] == "emporter"
        assert data["table"] is None
        assert data["client_adresse_livraison"] is None
        assert data["client_display"] == "Fatou"

    def test_livraison_sans_telephone_refusee(self, api_client, user_factory, restaurant_factory):
        serveur, _, plat = _staff_setup(user_factory, restaurant_factory)
        api_client._authenticate(serveur)

        res = api_client.post("/api/commandes/creer/", {
            "type_commande": "livraison",
            "client_adresse_livraison": "Kipé, Conakry",
            "items": [{"plat_id": plat.id, "quantite": 1}],
        }, format="json")

        assert res.status_code == 400
        assert "client_telephone" in res.data["errors"]

    def test_livraison_sans_adresse_refusee(self, api_client, user_factory, restaurant_factory):
        serveur, _, plat = _staff_setup(user_factory, restaurant_factory)
        api_client._authenticate(serveur)

        res = api_client.post("/api/commandes/creer/", {
            "type_commande": "livraison",
            "client_telephone": "+224620000003",
            "items": [{"plat_id": plat.id, "quantite": 1}],
        }, format="json")

        assert res.status_code == 400
        assert "client_adresse_livraison" in res.data["errors"]

    def test_sur_table_sans_table_refusee(self, api_client, user_factory, restaurant_factory):
        serveur, _, plat = _staff_setup(user_factory, restaurant_factory)
        api_client._authenticate(serveur)

        res = api_client.post("/api/commandes/creer/", {
            "items": [{"plat_id": plat.id, "quantite": 1}],
        }, format="json")

        assert res.status_code == 400
        assert "table_id" in res.data["errors"]
