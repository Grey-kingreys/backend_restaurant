# apps/commandes/serializers.py
from rest_framework import serializers
from django.db import transaction
from .models import Commande, CommandeItem, PanierItem
from apps.menu.models import Plat
from apps.menu.serializers import PlatListSerializer
from apps.restaurant.models import TableSession


# ─────────────────────────────────────────────────────────────────────────────
# PANIER
# ─────────────────────────────────────────────────────────────────────────────

class PanierItemSerializer(serializers.ModelSerializer):
    plat_detail = PlatListSerializer(source='plat', read_only=True)
    sous_total   = serializers.SerializerMethodField()

    class Meta:
        model  = PanierItem
        fields = ['id', 'plat', 'plat_detail', 'quantite', 'sous_total', 'date_ajout']
        read_only_fields = ['id', 'date_ajout']
        extra_kwargs = {'plat': {'write_only': True}}

    def get_sous_total(self, obj):
        return str(obj.sous_total)


class PanierItemCreateSerializer(serializers.Serializer):
    plat_id  = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1, max_value=10)

    def validate_plat_id(self, value):
        request = self.context['request']
        try:
            plat = Plat.objects.get(
                pk=value,
                restaurant=request.user.restaurant,
                disponible=True
            )
        except Plat.DoesNotExist:
            raise serializers.ValidationError(
                "Plat introuvable ou non disponible dans ce restaurant."
            )
        self._plat = plat
        return value

    def validate(self, data):
        data['plat'] = self._plat
        return data

    def save_to_panier(self, table):
        plat     = self.validated_data['plat']
        quantite = self.validated_data['quantite']
        item, _  = PanierItem.objects.update_or_create(
            table=table, plat=plat,
            defaults={'quantite': quantite}
        )
        return item


# ─────────────────────────────────────────────────────────────────────────────
# COMMANDE — Lecture
# ─────────────────────────────────────────────────────────────────────────────

class CommandeItemSerializer(serializers.ModelSerializer):
    plat_nom                      = serializers.CharField(source='plat.nom', read_only=True)
    plat_categorie                = serializers.CharField(source='plat.categorie', read_only=True)
    sous_total                    = serializers.SerializerMethodField()
    necessite_validation_cuisine  = serializers.BooleanField(
        source='plat.necessite_validation_cuisine', read_only=True
    )

    class Meta:
        model  = CommandeItem
        fields = [
            'id', 'plat', 'plat_nom', 'plat_categorie',
            'quantite', 'prix_unitaire', 'sous_total',
            'necessite_validation_cuisine',
        ]

    def get_sous_total(self, obj):
        return str(obj.sous_total)


class CommandeListSerializer(serializers.ModelSerializer):
    """Lecture allégée — pour les listes (toutes les vues)."""
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    table_login    = serializers.CharField(source='table.login', read_only=True)
    nb_items       = serializers.SerializerMethodField()

    class Meta:
        model  = Commande
        fields = [
            'id', 'table', 'table_login', 'statut', 'statut_display',
            'montant_total', 'nb_items',
            'date_commande', 'date_modification',
        ]

    def get_nb_items(self, obj):
        return obj.items.count()


class CommandeDetailSerializer(serializers.ModelSerializer):
    """Lecture complète — pour le détail (toutes les vues)."""
    items                   = CommandeItemSerializer(many=True, read_only=True)
    statut_display          = serializers.CharField(source='get_statut_display', read_only=True)
    table_login             = serializers.CharField(source='table.login', read_only=True)
    serveur_login           = serializers.SerializerMethodField()
    cuisinier_login         = serializers.SerializerMethodField()
    necessite_passage_cuisine = serializers.SerializerMethodField()
    peut_etre_marquee_prete = serializers.BooleanField(read_only=True)
    peut_etre_servie        = serializers.BooleanField(read_only=True)
    peut_etre_payee         = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Commande
        fields = [
            'id', 'restaurant', 'table', 'table_login', 'session',
            'statut', 'statut_display', 'montant_total',
            'serveur_ayant_servi', 'serveur_login',
            'cuisinier_ayant_prepare', 'cuisinier_login',
            'items',
            'peut_etre_marquee_prete', 'peut_etre_servie', 'peut_etre_payee',
            'necessite_passage_cuisine',
            'date_commande', 'date_modification', 'date_paiement',
        ]

    def get_serveur_login(self, obj):
        return obj.serveur_ayant_servi.login if obj.serveur_ayant_servi else None

    def get_cuisinier_login(self, obj):
        return obj.cuisinier_ayant_prepare.login if obj.cuisinier_ayant_prepare else None

    def get_necessite_passage_cuisine(self, obj):
        return obj.necessite_passage_cuisine()


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION PANIER → COMMANDE (Table)
# ─────────────────────────────────────────────────────────────────────────────

class CommandeValiderSerializer(serializers.Serializer):
    """
    Valide le panier et crée une commande EN_ATTENTE liée à la session QR active.
    CDC §10.3 : chaque commande est associée à une SessionTable au moment de sa création.
    """

    def validate(self, data):
        request = self.context['request']
        table   = request.user

        items = PanierItem.objects.filter(table=table).select_related('plat')
        if not items.exists():
            raise serializers.ValidationError("Votre panier est vide.")

        indisponibles = [i.plat.nom for i in items if not i.plat.disponible]
        if indisponibles:
            raise serializers.ValidationError(
                f"Plats non disponibles : {', '.join(indisponibles)}."
            )

        data['items'] = items
        data['table'] = table
        return data

    @transaction.atomic
    def create(self):
        data   = self.validated_data
        table  = data['table']
        items  = data['items']

        montant_total = sum(i.plat.prix_unitaire * i.quantite for i in items)

        # Récupérer la session QR active — obligatoire selon CDC §8.3 / §10.3
        session = None
        try:
            session = TableSession.objects.get(table=table, est_active=True)
        except TableSession.DoesNotExist:
            pass

        commande = Commande.objects.create(
            restaurant=table.restaurant,
            table=table,
            session=session,
            montant_total=montant_total,
            statut='en_attente',
        )

        CommandeItem.objects.bulk_create([
            CommandeItem(
                commande=commande,
                plat=item.plat,
                quantite=item.quantite,
                prix_unitaire=item.plat.prix_unitaire,
            )
            for item in items
        ])

        PanierItem.objects.filter(table=table).delete()
        return commande


# ─────────────────────────────────────────────────────────────────────────────
# VUE CUISINE
# ─────────────────────────────────────────────────────────────────────────────

class CommandeCuisinierSerializer(serializers.ModelSerializer):
    """Vue cuisine : commandes en_attente avec items nécessitant cuisine."""
    items          = CommandeItemSerializer(many=True, read_only=True)
    items_cuisine  = serializers.SerializerMethodField()
    table_login    = serializers.CharField(source='table.login', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)

    class Meta:
        model  = Commande
        fields = [
            'id', 'table_login', 'statut', 'statut_display',
            'montant_total', 'items', 'items_cuisine', 'date_commande',
        ]

    def get_items_cuisine(self, obj):
        items = obj.items.filter(plat__necessite_validation_cuisine=True)
        return CommandeItemSerializer(items, many=True).data


class CommandePreteSerializer(serializers.Serializer):
    """Marquer une commande comme PRÊTE (Cuisinier / Chef Cuisinier)."""

    def validate(self, data):
        commande = self.context['commande']
        if not commande.peut_etre_marquee_prete():
            raise serializers.ValidationError(
                f"Impossible — statut actuel : {commande.get_statut_display()}."
            )
        return data

    def save(self, cuisinier):
        commande = self.context['commande']
        commande.cuisinier_ayant_prepare = cuisinier
        commande.statut = 'prete'
        commande.save(update_fields=['statut', 'cuisinier_ayant_prepare', 'date_modification'])
        return commande


# ─────────────────────────────────────────────────────────────────────────────
# VUE SERVEUR
# CDC §7.1 étapes 4 & 5 : Serveur → SERVIE puis PAYÉE
# CDC §5.2 : Serveur voit toutes les commandes actives + marque SERVIE + PAYÉE
# ─────────────────────────────────────────────────────────────────────────────

class CommandeServieSerializer(serializers.Serializer):
    """
    Marquer une commande comme SERVIE (Serveur).
    CDC §7.1 étape 4.
    Règle : statut doit être 'prete' OU tous les plats de la commande
    n'ont pas besoin de passage cuisine (étape cuisine sautée → SERVIE directe).
    """

    def validate(self, data):
        commande = self.context['commande']
        if not commande.peut_etre_servie():
            raise serializers.ValidationError(
                f"Impossible de marquer comme SERVIE — statut actuel : "
                f"{commande.get_statut_display()}. "
                "La commande doit être PRÊTE ou ne nécessiter aucune validation cuisine."
            )
        return data

    def save(self, serveur):
        commande = self.context['commande']
        commande.serveur_ayant_servi = serveur
        commande.statut = 'servie'
        commande.save(update_fields=['statut', 'serveur_ayant_servi', 'date_modification'])
        return commande


class CommandePayeeSerializer(serializers.Serializer):
    """
    Marquer une commande comme PAYÉE (Serveur).
    CDC §7.1 étape 5 — crée une transaction en attente de remise au comptable.
    La commande doit être en statut 'servie'.
    """

    def validate(self, data):
        commande = self.context['commande']
        if not commande.peut_etre_payee():
            raise serializers.ValidationError(
                f"Impossible de marquer comme PAYÉE — statut actuel : "
                f"{commande.get_statut_display()}. "
                "La commande doit d'abord être SERVIE."
            )
        return data

    @transaction.atomic
    def save(self, serveur):
        from django.utils import timezone as tz
        from apps.paiements.models import Paiement
 
        commande = self.context['commande']
        commande.serveur_ayant_servi = serveur
        commande.statut       = 'payee'
        commande.date_paiement = tz.now()
        commande.save(update_fields=[
            'statut', 'serveur_ayant_servi', 'date_paiement', 'date_modification'
        ])
 
        # ── Creer le Paiement ──────────────────────────────────────────
        paiement, created = Paiement.objects.get_or_create(
            commande=commande,
            defaults={'montant': commande.montant_total},
        )
 
        # ── Declencher la creation de la RemiseServeur (async) ─────────
        if created:
            try:
                from apps.paiements.tasks import creer_remise_pour_paiement
                creer_remise_pour_paiement.delay(paiement.id)
            except Exception:
                # Ne pas bloquer le flux si Celery est indisponible
                import logging
                logging.getLogger(__name__).warning(
                    "Impossible de planifier creer_remise_pour_paiement "
                    "pour paiement %d — Celery indisponible ?",
                    paiement.id,
                )
 
        # ── Declencher la verification d'expiration de session QR ──────
        if commande.session:
            try:
                from apps.restaurant.tasks import verifier_expiration_session
                verifier_expiration_session.apply_async(
                    args=[commande.session.id],
                    countdown=60  # 1 minute
                )
            except Exception:
                pass
 
        return commande