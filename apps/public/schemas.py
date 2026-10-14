# apps/public/schemas.py
# Serializers de documentation OpenAPI des vues publiques : ils décrivent les corps
# de requête lus à la main et les dicts renvoyés par apps/public/api_views.py.
# Jamais utilisés à l'exécution.

from rest_framework import serializers


# ── Requêtes ─────────────────────────────────────────────────────────────────

class InscriptionClientRequeteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, help_text="8 caractères minimum.")
    password_confirm = serializers.CharField(help_text="Doit être identique à password.")
    nom_complet = serializers.CharField()
    telephone = serializers.CharField(required=False, allow_blank=True)


class ContactRequeteSerializer(serializers.Serializer):
    nom = serializers.CharField()
    email = serializers.EmailField()
    message = serializers.CharField(max_length=5000)


class CommanderArticleRequeteSerializer(serializers.Serializer):
    plat_id = serializers.IntegerField()
    quantite = serializers.IntegerField(required=False, default=1, min_value=1)


class CommanderRequeteSerializer(serializers.Serializer):
    type_commande = serializers.ChoiceField(
        choices=['livraison', 'emporter'], required=False, default='livraison',
    )
    mode_paiement = serializers.CharField(
        required=False, default='livraison',
        help_text="Seul 'livraison' (paiement à la livraison) est accepté pour l'instant.",
    )
    adresse_livraison = serializers.CharField(
        required=False, allow_blank=True, help_text="Obligatoire pour une livraison.",
    )
    telephone = serializers.CharField(
        required=False, allow_blank=True,
        help_text="Par défaut, le téléphone du compte client.",
    )
    latitude = serializers.FloatField(
        required=False, allow_null=True, help_text="Position choisie sur la carte (livraison).",
    )
    longitude = serializers.FloatField(required=False, allow_null=True)
    items = CommanderArticleRequeteSerializer(many=True)


class AnnulerCommandeRequeteSerializer(serializers.Serializer):
    motif = serializers.CharField(required=False, allow_blank=True)


class ReserverRequeteSerializer(serializers.Serializer):
    date = serializers.CharField(help_text="Format AAAA-MM-JJ.")
    heure = serializers.CharField(help_text="Format HH:MM.")
    nombre_personnes = serializers.IntegerField(required=False, default=1, min_value=1)
    note = serializers.CharField(required=False, allow_blank=True)


class ActionLivraisonRequeteSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['en_livraison', 'servie', 'payee'])


# ── Réponses ─────────────────────────────────────────────────────────────────

class UtilisateurClientDocSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    nom_complet = serializers.CharField()
    telephone = serializers.CharField(allow_null=True)
    role = serializers.CharField()


class InscriptionClientDocSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="Jeton d'accès JWT.")
    refresh = serializers.CharField(help_text="Jeton de rafraîchissement JWT.")
    user = UtilisateurClientDocSerializer()


class RestaurantPublicDocSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nom = serializers.CharField()
    slug = serializers.CharField()
    adresse = serializers.CharField(allow_null=True)
    telephone = serializers.CharField()
    latitude = serializers.CharField(allow_null=True, help_text="Décimal en texte.")
    longitude = serializers.CharField(allow_null=True, help_text="Décimal en texte.")
    accept_livraison = serializers.BooleanField()
    accept_emporter = serializers.BooleanField()


class RestaurantListeDocSerializer(serializers.Serializer):
    restaurants = RestaurantPublicDocSerializer(many=True)
    count = serializers.IntegerField()


class PlatMenuPublicDocSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nom = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    prix_unitaire = serializers.CharField(help_text="Décimal en texte.")
    categorie = serializers.CharField()
    image_url = serializers.CharField(allow_null=True)
    necessite_validation_cuisine = serializers.BooleanField()


class RestaurantDetailDocSerializer(serializers.Serializer):
    restaurant = RestaurantPublicDocSerializer()
    plats = PlatMenuPublicDocSerializer(many=True)
    count_plats = serializers.IntegerField()


class RestaurantDuPlatDocSerializer(serializers.Serializer):
    nom = serializers.CharField()
    slug = serializers.CharField()
    adresse = serializers.CharField(allow_null=True)
    latitude = serializers.CharField(allow_null=True, help_text="Décimal en texte.")
    longitude = serializers.CharField(allow_null=True, help_text="Décimal en texte.")


class PlatPublicDocSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nom = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    prix_unitaire = serializers.CharField(help_text="Décimal en texte.")
    categorie = serializers.CharField()
    image_url = serializers.CharField(allow_null=True)
    restaurant = RestaurantDuPlatDocSerializer()


class PlatsPublicsListeDocSerializer(serializers.Serializer):
    plats = PlatPublicDocSerializer(many=True)
    count = serializers.IntegerField()


class CommandeCreeeDocSerializer(serializers.Serializer):
    commande_id = serializers.IntegerField()
    cle_suivi = serializers.CharField(help_text="Clé secrète pour le suivi public de la commande.")
    statut = serializers.CharField()
    montant_total = serializers.CharField(help_text="Décimal en texte.")
    type_commande = serializers.CharField()
    mode_paiement = serializers.CharField()
    suivi_url = serializers.CharField(help_text="URL absolue de la page de suivi de la commande.")


class CommandeClientDocSerializer(serializers.Serializer):
    commande_id = serializers.IntegerField()
    cle_suivi = serializers.CharField(allow_null=True)
    restaurant = serializers.CharField()
    restaurant_slug = serializers.CharField()
    statut = serializers.CharField()
    statut_label = serializers.CharField()
    type_commande = serializers.CharField()
    mode_paiement = serializers.CharField(allow_null=True)
    montant_total = serializers.CharField(help_text="Décimal en texte.")
    nb_items = serializers.IntegerField()
    annulable = serializers.BooleanField()
    motif_annulation = serializers.CharField(allow_null=True)
    date_commande = serializers.DateTimeField()


class StatsCommandesClientDocSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    en_cours = serializers.IntegerField()
    total_depense = serializers.CharField(help_text="Somme des commandes payées, en texte.")


class MesCommandesDocSerializer(serializers.Serializer):
    commandes = CommandeClientDocSerializer(many=True)
    stats = StatsCommandesClientDocSerializer()


class CommandeAnnuleeDocSerializer(serializers.Serializer):
    commande_id = serializers.IntegerField()
    statut = serializers.CharField()
    statut_label = serializers.CharField()


class TablesDisponiblesDocSerializer(serializers.Serializer):
    disponible = serializers.BooleanField()
    message = serializers.CharField()
    duree_minutes = serializers.IntegerField()
    heure_fin = serializers.CharField(help_text="Format HH:MM.")
    capacite_max = serializers.IntegerField(help_text="Plus grande table du restaurant, 0 si aucune.")


class ReservationClientDocSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    restaurant = serializers.CharField()
    restaurant_slug = serializers.CharField()
    date_reservation = serializers.DateField()
    heure = serializers.CharField(help_text="Format HH:MM.")
    heure_fin = serializers.CharField(help_text="Format HH:MM.")
    duree_minutes = serializers.IntegerField()
    nombre_personnes = serializers.IntegerField()
    note = serializers.CharField()
    statut = serializers.CharField()
    statut_label = serializers.CharField()
    annulable = serializers.BooleanField()
    delai_annulation_heures = serializers.IntegerField()
    date_creation = serializers.DateTimeField()


class MesReservationsDocSerializer(serializers.Serializer):
    reservations = ReservationClientDocSerializer(many=True)
    count = serializers.IntegerField()


class SuiviArticleDocSerializer(serializers.Serializer):
    nom = serializers.CharField()
    quantite = serializers.IntegerField()
    prix_unitaire = serializers.CharField(help_text="Décimal en texte.")
    sous_total = serializers.CharField(help_text="Décimal en texte.")


class SuiviCommandeDocSerializer(serializers.Serializer):
    commande_id = serializers.IntegerField()
    restaurant = serializers.CharField()
    statut = serializers.CharField()
    statut_label = serializers.CharField()
    statut_index = serializers.IntegerField(help_text="Position de l'étape courante dans le parcours.")
    statut_total = serializers.IntegerField(help_text="Nombre d'étapes du parcours de cette commande.")
    necessite_passage_cuisine = serializers.BooleanField()
    type_commande = serializers.CharField()
    mode_paiement = serializers.CharField(allow_null=True)
    montant_total = serializers.CharField(help_text="Décimal en texte.")
    adresse_livraison = serializers.CharField(allow_null=True)
    date_commande = serializers.DateTimeField()
    items = SuiviArticleDocSerializer(many=True)


class LivraisonArticleDocSerializer(serializers.Serializer):
    nom = serializers.CharField()
    quantite = serializers.IntegerField()
    sous_total = serializers.CharField(help_text="Décimal en texte.")


class LivraisonActionsDocSerializer(serializers.Serializer):
    peut_passer_en_livraison = serializers.BooleanField()
    peut_etre_servie = serializers.BooleanField()
    peut_encaisser = serializers.BooleanField()


class LivraisonPubliqueDocSerializer(serializers.Serializer):
    commande_id = serializers.IntegerField()
    restaurant = serializers.CharField()
    restaurant_telephone = serializers.CharField()
    statut = serializers.CharField()
    statut_label = serializers.CharField()
    client_nom = serializers.CharField(allow_null=True)
    client_telephone = serializers.CharField(allow_null=True)
    adresse_livraison = serializers.CharField(allow_null=True)
    latitude = serializers.CharField(allow_null=True, help_text="Décimal en texte.")
    longitude = serializers.CharField(allow_null=True, help_text="Décimal en texte.")
    mode_paiement = serializers.CharField(allow_null=True)
    montant_total = serializers.CharField(help_text="Décimal en texte.")
    items = LivraisonArticleDocSerializer(many=True)
    paiement_autorise = serializers.BooleanField()
    actions = LivraisonActionsDocSerializer()
