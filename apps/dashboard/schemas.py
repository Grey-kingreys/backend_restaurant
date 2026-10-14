# apps/dashboard/schemas.py
# Serializers de documentation OpenAPI du tableau de bord : une variante par type de
# compte, relevée dans les méthodes _dashboard_* de apps/dashboard/views.py.
# Le champ `type` est le discriminant. Jamais utilisés à l'exécution.

from rest_framework import serializers


# ── Blocs communs ────────────────────────────────────────────────────────────

class CommandeResumeDocSerializer(serializers.Serializer):
    """Commande résumée (_fmt_commande)."""
    id = serializers.IntegerField()
    table = serializers.CharField(help_text="Libellé de la table, ou nom du client, ou type de commande.")
    montant = serializers.CharField(help_text="Décimal en texte.")
    statut = serializers.CharField()
    heure = serializers.CharField(help_text="Format HH:MM.")


class RevenuJourDocSerializer(serializers.Serializer):
    date = serializers.CharField(help_text="Format JJ/MM.")
    revenus = serializers.FloatField()
    commandes = serializers.IntegerField()


class ActiviteHeureDocSerializer(serializers.Serializer):
    h = serializers.CharField(help_text="Heure, par exemple 08h.")
    n = serializers.IntegerField(help_text="Nombre de commandes.")


class RepartitionCategorieDocSerializer(serializers.Serializer):
    categorie = serializers.CharField()
    label = serializers.CharField()
    total = serializers.IntegerField()


# ── Admin ────────────────────────────────────────────────────────────────────

class KpisAdminDocSerializer(serializers.Serializer):
    revenus_jour = serializers.CharField(help_text="Décimal en texte.")
    commandes_jour = serializers.IntegerField()
    ticket_moyen = serializers.CharField(help_text="Décimal en texte.")
    tables_occupees = serializers.IntegerField()
    tables_total = serializers.IntegerField()
    commandes_en_attente = serializers.IntegerField()
    commandes_pretes = serializers.IntegerField()
    depenses_jour = serializers.CharField(help_text="Décimal en texte.")
    benefice_net = serializers.CharField(help_text="Décimal en texte.")
    solde_generale = serializers.CharField(help_text="Décimal en texte.")


class StatutLiveDocSerializer(serializers.Serializer):
    statut = serializers.CharField()
    total = serializers.IntegerField()
    label = serializers.CharField()


class TopPlatAdminDocSerializer(serializers.Serializer):
    nom = serializers.CharField()
    categorie = serializers.CharField()
    total = serializers.IntegerField()


class DashboardAdminDocSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['admin'])
    kpis = KpisAdminDocSerializer()
    revenus_7j = RevenuJourDocSerializer(many=True)
    statuts_live = StatutLiveDocSerializer(many=True)
    par_categorie = RepartitionCategorieDocSerializer(many=True)
    par_heure = ActiviteHeureDocSerializer(many=True)
    top_plats = TopPlatAdminDocSerializer(many=True)
    dernieres_commandes = CommandeResumeDocSerializer(many=True)


# ── Serveur ──────────────────────────────────────────────────────────────────

class TableStatutDocSerializer(serializers.Serializer):
    numero = serializers.CharField()
    places = serializers.IntegerField()
    statut = serializers.CharField()


class DashboardServeurTypeDocSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['serveur'])
    tables_actives = CommandeResumeDocSerializer(many=True)
    commandes_pretes = CommandeResumeDocSerializer(many=True)
    nb_tables_actives = serializers.IntegerField()
    nb_commandes_pretes = serializers.IntegerField()
    remises_jour = serializers.CharField(help_text="Décimal en texte.")
    commandes_traitees_7j = serializers.IntegerField()
    par_heure = ActiviteHeureDocSerializer(many=True)
    tables_statuts = TableStatutDocSerializer(many=True)
    revenus_actifs = serializers.CharField(help_text="Décimal en texte.")


# ── Livreur ──────────────────────────────────────────────────────────────────

class KpisLivreurDocSerializer(serializers.Serializer):
    a_expedier = serializers.IntegerField()
    en_cours = serializers.IntegerField()
    livrees_jour = serializers.IntegerField()


class LivraisonResumeDocSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    client = serializers.CharField(help_text="Nom du client, ou un tiret s'il est inconnu.")
    adresse = serializers.CharField(help_text="Chaîne vide si l'adresse est inconnue.")
    montant = serializers.CharField(help_text="Décimal en texte.")
    statut = serializers.CharField()
    heure = serializers.CharField(help_text="Format HH:MM.")


class DashboardLivreurDocSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['livreur'])
    kpis = KpisLivreurDocSerializer()
    livraisons = LivraisonResumeDocSerializer(many=True, help_text="20 livraisons au plus.")


# ── Cuisine ──────────────────────────────────────────────────────────────────

class ArticleCuisineDocSerializer(serializers.Serializer):
    plat = serializers.CharField()
    quantite = serializers.IntegerField()


class CommandeCuisineDocSerializer(CommandeResumeDocSerializer):
    items = ArticleCuisineDocSerializer(many=True)
    attente_mins = serializers.IntegerField(help_text="Minutes d'attente depuis la commande.")


class TopPlatJourDocSerializer(serializers.Serializer):
    nom = serializers.CharField()
    total = serializers.IntegerField()


class DashboardCuisineDocSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['cuisine'])
    file_commandes = CommandeCuisineDocSerializer(many=True)
    nb_en_attente = serializers.IntegerField()
    nb_pretes = serializers.IntegerField()
    top_plats_jour = TopPlatJourDocSerializer(many=True)
    par_categorie = RepartitionCategorieDocSerializer(many=True)
    par_heure = ActiviteHeureDocSerializer(many=True)
    total_plats_7j = serializers.IntegerField()
    oldest_wait_mins = serializers.IntegerField(
        allow_null=True, help_text="Attente de la plus ancienne commande en attente, null s'il n'y en a pas.",
    )


# ── Comptable ────────────────────────────────────────────────────────────────

class CaisseComptableResumeDocSerializer(serializers.Serializer):
    solde = serializers.CharField(help_text="Décimal en texte.")
    is_open = serializers.BooleanField()
    opened_at = serializers.CharField(allow_null=True, help_text="Format HH:MM, null si aucune caisse ouverte.")


class BalanceJourDocSerializer(serializers.Serializer):
    date = serializers.CharField(help_text="Format JJ/MM.")
    revenus = serializers.FloatField()
    depenses = serializers.FloatField()


class RemiseResumeDocSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    montant = serializers.CharField(help_text="Décimal en texte.")
    valide = serializers.BooleanField()
    table = serializers.CharField(help_text="Libellé de la table, ou un tiret s'il est inconnu.")
    serveur = serializers.CharField(help_text="Nom du serveur, ou un tiret s'il est inconnu.")
    date = serializers.CharField(help_text="Format JJ/MM HH:MM.")


class DashboardComptableTypeDocSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['comptable'])
    caisse = CaisseComptableResumeDocSerializer()
    remises_en_attente = serializers.IntegerField()
    depenses_jour = serializers.CharField(help_text="Décimal en texte.")
    revenus_jour = serializers.CharField(help_text="Décimal en texte.")
    benefice_net = serializers.CharField(help_text="Décimal en texte.")
    cmds_payees_jour = serializers.IntegerField()
    solde_generale = serializers.CharField(help_text="Décimal en texte.")
    balance_7j = BalanceJourDocSerializer(many=True)
    dernieres_remises = RemiseResumeDocSerializer(many=True)


# ── Table ────────────────────────────────────────────────────────────────────

class ArticleTableDocSerializer(serializers.Serializer):
    plat = serializers.CharField()
    quantite = serializers.IntegerField()
    prix = serializers.CharField(help_text="Décimal en texte.")


class CommandeActiveTableDocSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    statut = serializers.CharField()
    montant = serializers.CharField(help_text="Décimal en texte.")
    heure = serializers.CharField(help_text="Format HH:MM.")
    attente_mins = serializers.IntegerField()
    items = ArticleTableDocSerializer(many=True)


class SuggestionDocSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nom = serializers.CharField()
    categorie = serializers.CharField()
    prix = serializers.CharField(help_text="Décimal en texte.")
    commandes = serializers.IntegerField(help_text="Quantité totale commandée.")


class DashboardTableDocSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['table'])
    commande_active = CommandeActiveTableDocSerializer(allow_null=True)
    nb_plats_disponibles = serializers.IntegerField()
    suggestions = SuggestionDocSerializer(many=True)


# ── Super admin ──────────────────────────────────────────────────────────────

class RevenuGlobalJourDocSerializer(serializers.Serializer):
    date = serializers.CharField(help_text="Format JJ/MM.")
    revenus = serializers.FloatField()


class StatsRestaurantDocSerializer(serializers.Serializer):
    nom = serializers.CharField()
    revenus_jour = serializers.CharField(help_text="Décimal en texte.")
    commandes_actives = serializers.IntegerField()


class DashboardSuperadminDocSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['superadmin'])
    total_restaurants = serializers.IntegerField()
    total_users = serializers.IntegerField()
    revenus_global_jour = serializers.CharField(help_text="Décimal en texte.")
    commandes_global_jour = serializers.IntegerField()
    revenus_7j = RevenuGlobalJourDocSerializer(many=True)
    stats_restaurants = StatsRestaurantDocSerializer(many=True)
