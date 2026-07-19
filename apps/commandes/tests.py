"""Tests app commandes — sessions de table & mes-commandes."""
import pytest
from apps.restaurant.models import TableSession


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
