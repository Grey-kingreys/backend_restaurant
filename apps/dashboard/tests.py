"""Tests app dashboard - accès à /api/dashboard/stats/ selon le type de compte."""
import pytest


URL = "/api/dashboard/stats/"


@pytest.mark.django_db
class TestDashboardAcces:
    """Le tableau de bord n'est servi qu'aux comptes qui ont un type reconnu."""

    def test_client_refuse(self, api_client, user_factory):
        """Régression : un client (inscription libre, sans role_config) recevait
        le tableau de bord super admin, donc les chiffres de toute la plateforme.
        """
        client = user_factory(login="client_dash", email="client@example.com", role="Rclient")
        # Comme à l'inscription publique : client rattaché à aucun restaurant.
        client.restaurant = None
        client.save(update_fields=["restaurant"])
        api_client._authenticate(client)
        res = api_client.get(URL)

        assert res.status_code == 403
        assert res.data["success"] is False
        assert "revenus_global" not in str(res.data)

    def test_personnel_sans_role_config_refuse(self, api_client, user_factory):
        """Un compte du personnel sans role_config n'a pas de type de tableau
        de bord : il ne doit pas retomber sur celui du super admin."""
        serveur = user_factory(login="serveur_dash", email="s@example.com", role="Rserveur")
        assert serveur.role_config_id is None
        api_client._authenticate(serveur)
        res = api_client.get(URL)

        assert res.status_code == 403

    def test_super_admin_garde_son_tableau_de_bord(self, api_client, user_factory):
        admin = user_factory(login="sa_dash", email="sa@example.com", role="Rsuper_admin")
        api_client._authenticate(admin)
        res = api_client.get(URL)

        assert res.status_code == 200
        assert res.data["data"]["type"] == "superadmin"
