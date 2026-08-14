"""Tests du flux de caisse — intégrité des soldes.

Régression : les crédits/débits faisaient un read-modify-write sur `self.solde`
sans verrou (perte de mise à jour possible en concurrence). Ils passent
désormais par des updates atomiques `F()` (décrément conditionnel pour les
débits), et les `fermer()` par `select_for_update()` sous `@transaction.atomic`.
"""
import pytest
from decimal import Decimal
from django.utils import timezone
from apps.paiements.exceptions import ErreurMetier
from apps.paiements.models import (
    CaisseGenerale, CaisseGlobale, CaisseComptable, DemandeApprovisionnement,
)


@pytest.mark.django_db
class TestCaisseSolde:

    def _generale(self, restaurant_factory, solde="1000.00"):
        r = restaurant_factory()
        return CaisseGenerale.objects.create(restaurant=r, solde=Decimal(solde))

    def test_crediter_debiter_soldes_corrects(self, restaurant_factory):
        cg = self._generale(restaurant_factory, "1000.00")
        cg.crediter(Decimal("250.00"))
        assert cg.solde == Decimal("1250.00")          # instance à jour
        cg.refresh_from_db()
        assert cg.solde == Decimal("1250.00")          # DB à jour
        cg.debiter(Decimal("300.00"))
        assert cg.solde == Decimal("950.00")

    def test_debiter_solde_insuffisant_refuse_et_ne_bouge_pas(self, restaurant_factory):
        cg = self._generale(restaurant_factory, "100.00")
        with pytest.raises(ValueError):
            cg.debiter(Decimal("150.00"))
        cg.refresh_from_db()
        assert cg.solde == Decimal("100.00")           # solde inchangé

    def test_crediter_globale_fermee_refuse(self, restaurant_factory):
        r = restaurant_factory()
        CaisseGenerale.objects.create(restaurant=r, solde=Decimal("0.00"))
        glob = CaisseGlobale.objects.create(
            restaurant=r, date_ouverture=timezone.now().date(),
            solde=Decimal("0.00"), is_closed=True,
        )
        with pytest.raises(ValueError):
            glob.crediter(Decimal("50.00"))

    def test_fermer_globale_transfere_et_idempotent(self, restaurant_factory):
        r = restaurant_factory()
        cg = CaisseGenerale.objects.create(restaurant=r, solde=Decimal("500.00"))
        glob = CaisseGlobale.objects.create(
            restaurant=r, date_ouverture=timezone.now().date(), solde=Decimal("300.00"),
        )
        glob.fermer(fermee_par=None, montant_physique=Decimal("300.00"))
        cg.refresh_from_db()
        assert cg.solde == Decimal("800.00")           # 500 + 300 transféré
        glob.refresh_from_db()
        assert glob.is_closed is True
        with pytest.raises(ValueError):                # 2ᵉ fermeture interdite
            glob.fermer(fermee_par=None, montant_physique=Decimal("300.00"))

    def test_comptable_debit_insuffisant_refuse(self, restaurant_factory):
        r = restaurant_factory()
        from django.contrib.auth import get_user_model
        comptable = get_user_model().objects.create_user(
            login="cpt", email="cpt@test.com", password="pass",
            role="Rcomptable", restaurant=r,
        )
        caisse = CaisseComptable.objects.create(
            restaurant=r, comptable=comptable, solde=Decimal("50.00"),
        )
        with pytest.raises(ValueError):
            caisse.debiter(Decimal("80.00"))
        caisse.refresh_from_db()
        assert caisse.solde == Decimal("50.00")


@pytest.mark.django_db
class TestApprovisionnementSansCaisseGenerale:
    """Régression : valider un appro sur un restaurant sans Caisse Générale
    levait `RelatedObjectDoesNotExist` (HTTP 500) au lieu d'une erreur métier.
    Seuls le seed et `/caisse-generale/init/` créaient le coffre : les
    restaurants nés de l'onboarding n'en avaient aucun."""

    def _demande(self, restaurant, montant="100000.00"):
        from django.contrib.auth import get_user_model
        comptable = get_user_model().objects.create_user(
            login="cpt_appro", email="cpt_appro@test.com", password="pass",
            role="Rcomptable", restaurant=restaurant,
        )
        caisse = CaisseComptable.objects.create(
            restaurant=restaurant, comptable=comptable, solde=Decimal("0.00"),
        )
        return DemandeApprovisionnement.objects.create(
            restaurant=restaurant, caisse_comptable=caisse,
            montant=Decimal(montant), motif="Fonds de roulement",
            demande_par=comptable,
        )

    def test_approuver_sans_coffre_leve_erreur_metier(self, restaurant_factory):
        r = restaurant_factory()
        assert not CaisseGenerale.objects.filter(restaurant=r).exists()
        demande = self._demande(r)

        with pytest.raises(ErreurMetier):        # -> HTTP 400, plus 500
            demande.approuver(validee_par=None)

        demande.refresh_from_db()
        assert demande.statut == 'en_attente'    # demande toujours validable

    def test_approuver_avec_coffre_credite_transfere(self, restaurant_factory):
        r = restaurant_factory()
        cg = CaisseGenerale.objects.create(restaurant=r, solde=Decimal("500000.00"))
        demande = self._demande(r, "100000.00")

        demande.approuver(validee_par=None)

        cg.refresh_from_db()
        assert cg.solde == Decimal("400000.00")
        demande.caisse_comptable.refresh_from_db()
        assert demande.caisse_comptable.solde == Decimal("100000.00")
        assert demande.statut == 'approuvee'

    def test_pour_restaurant_cree_le_coffre_une_seule_fois(self, restaurant_factory):
        r = restaurant_factory()
        premier = CaisseGenerale.pour_restaurant(r)
        second = CaisseGenerale.pour_restaurant(r)
        assert premier.pk == second.pk
        assert CaisseGenerale.objects.filter(restaurant=r).count() == 1

    def test_fermer_comptable_sans_coffre_ne_perd_pas_l_argent(self, restaurant_factory):
        r = restaurant_factory()
        from django.contrib.auth import get_user_model
        comptable = get_user_model().objects.create_user(
            login="cpt_ferm", email="cpt_ferm@test.com", password="pass",
            role="Rcomptable", restaurant=r,
        )
        caisse = CaisseComptable.objects.create(
            restaurant=r, comptable=comptable, solde=Decimal("70000.00"),
        )

        caisse.fermer(montant_physique=Decimal("70000.00"), fermee_par=comptable)

        assert CaisseGenerale.objects.get(restaurant=r).solde == Decimal("70000.00")
