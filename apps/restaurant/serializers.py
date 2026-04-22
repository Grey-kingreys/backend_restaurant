# apps/restaurant/serializers.py
"""
Phase 6 — Tables, QR Code, Sessions
Sérialiseurs DRF pour la gestion des tables physiques et sessions.

Architecture SaaS v2 :
- TableRestaurant : table physique liée à un User Rtable (OneToOne)
- TableToken     : token de connexion QR
- TableSession   : session de connexion (isolation commandes)
- User Rtable    : compte table, isolé par restaurant FK
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import TableRestaurant, TableToken, TableSession

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# TABLE RESTAURANT
# ─────────────────────────────────────────────────────────────────────────────

class TableRestaurantListSerializer(serializers.ModelSerializer):
    """
    Lecture allégée — liste des tables.
    Inclut le login du User Rtable associé et le statut courant.
    """
    utilisateur_login    = serializers.CharField(source='utilisateur.login', read_only=True)
    utilisateur_actif    = serializers.BooleanField(source='utilisateur.actif', read_only=True)
    statut_courant       = serializers.SerializerMethodField()
    a_qr_code            = serializers.SerializerMethodField()
    nb_commandes_actives = serializers.SerializerMethodField()

    class Meta:
        model  = TableRestaurant
        fields = [
            'id', 'numero_table', 'nombre_places',
            'utilisateur', 'utilisateur_login', 'utilisateur_actif',
            'statut_courant', 'a_qr_code', 'nb_commandes_actives',
            'date_creation', 'date_modification',
        ]

    def get_statut_courant(self, obj):
        """
        Statut en temps réel basé sur les commandes actives.
        libre | en_attente | prete | servie
        """
        from apps.commandes.models import Commande
        derniere = Commande.objects.filter(
            table=obj.utilisateur,
            statut__in=['en_attente', 'prete', 'servie']
        ).order_by('-date_commande').first()

        if not derniere:
            return 'libre'
        return derniere.statut

    def get_a_qr_code(self, obj):
        """True si un QR code valide existe pour cette table."""
        try:
            token = obj.utilisateur.auth_token
            return token.est_valide()
        except TableToken.DoesNotExist:
            return False

    def get_nb_commandes_actives(self, obj):
        from apps.commandes.models import Commande
        return Commande.objects.filter(
            table=obj.utilisateur,
            statut__in=['en_attente', 'prete', 'servie']
        ).count()


class TableRestaurantDetailSerializer(serializers.ModelSerializer):
    """Lecture complète — détail d'une table avec statistiques."""
    utilisateur_login = serializers.CharField(source='utilisateur.login', read_only=True)
    utilisateur_actif = serializers.BooleanField(source='utilisateur.actif', read_only=True)
    statut_courant    = serializers.SerializerMethodField()
    a_qr_code         = serializers.SerializerMethodField()
    commandes_actives = serializers.SerializerMethodField()
    stats             = serializers.SerializerMethodField()
    session_active    = serializers.SerializerMethodField()

    class Meta:
        model  = TableRestaurant
        fields = [
            'id', 'numero_table', 'nombre_places',
            'utilisateur', 'utilisateur_login', 'utilisateur_actif',
            'statut_courant', 'a_qr_code',
            'commandes_actives', 'session_active', 'stats',
            'date_creation', 'date_modification',
        ]

    def get_statut_courant(self, obj):
        from apps.commandes.models import Commande
        derniere = Commande.objects.filter(
            table=obj.utilisateur,
            statut__in=['en_attente', 'prete', 'servie']
        ).order_by('-date_commande').first()
        if not derniere:
            return 'libre'
        return derniere.statut

    def get_a_qr_code(self, obj):
        try:
            return obj.utilisateur.auth_token.est_valide()
        except TableToken.DoesNotExist:
            return False

    def get_commandes_actives(self, obj):
        from apps.commandes.models import Commande
        from apps.commandes.serializers import CommandeListSerializer
        qs = Commande.objects.filter(
            table=obj.utilisateur,
            statut__in=['en_attente', 'prete', 'servie']
        ).order_by('-date_commande')
        return CommandeListSerializer(qs, many=True).data

    def get_session_active(self, obj):
        try:
            session = TableSession.objects.get(
                table=obj.utilisateur,
                est_active=True
            )
            return {
                'id':             session.id,
                'session_token':  str(session.session_token),
                'date_creation':  session.date_creation,
                'date_paiement':  session.date_paiement,
            }
        except TableSession.DoesNotExist:
            return None

    def get_stats(self, obj):
        from apps.commandes.models import Commande
        from django.db.models import Sum
        qs = Commande.objects.filter(table=obj.utilisateur)
        return {
            'total_commandes':  qs.count(),
            'commandes_payees': qs.filter(statut='payee').count(),
            'montant_total':    str(
                qs.filter(statut='payee').aggregate(
                    total=Sum('montant_total')
                )['total'] or 0
            ),
        }


class TableRestaurantCreateSerializer(serializers.ModelSerializer):
    """
    Création d'une table physique (Admin uniquement).
    Le User associé doit être Rtable et appartenir au même restaurant.

    Le champ `restaurant` est intentionnellement absent de `fields` :
    il est injecté automatiquement depuis request.user.restaurant dans create()
    pour éviter tout risque d'injection cross-restaurant.
    """
    class Meta:
        model  = TableRestaurant
        fields = ['numero_table', 'nombre_places', 'utilisateur']

    def validate_utilisateur(self, value):
        request = self.context['request']

        # Doit être Rtable
        if not value.is_table():
            raise serializers.ValidationError(
                "L'utilisateur doit avoir le rôle Table (Rtable)."
            )

        # Doit appartenir au même restaurant
        if value.restaurant != request.user.restaurant:
            raise serializers.ValidationError(
                "Cet utilisateur n'appartient pas à votre restaurant."
            )

        # Ne doit pas déjà avoir une table associée
        instance = self.instance
        qs = TableRestaurant.objects.filter(utilisateur=value)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"Le compte {value.login} est déjà associé à une table."
            )
        return value

    def validate_numero_table(self, value):
        request  = self.context['request']
        instance = self.instance
        qs = TableRestaurant.objects.filter(
            numero_table=value.strip().upper(),
            utilisateur__restaurant=request.user.restaurant
        )
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"Le numéro de table '{value}' est déjà utilisé dans ce restaurant."
            )
        return value.strip().upper()

    def create(self, validated_data):
        # Injection du restaurant depuis l'admin connecté — non exposé dans le payload
        validated_data['restaurant'] = self.context['request'].user.restaurant
        return super().create(validated_data)


class TableRestaurantUpdateSerializer(TableRestaurantCreateSerializer):
    """Modification partielle d'une table (Admin)."""
    class Meta(TableRestaurantCreateSerializer.Meta):
        pass


# ─────────────────────────────────────────────────────────────────────────────
# QR CODE
# ─────────────────────────────────────────────────────────────────────────────

class QRCodeInfoSerializer(serializers.ModelSerializer):
    """Informations sur le QR code d'une table."""
    est_valide                = serializers.SerializerMethodField()
    date_derniere_utilisation = serializers.DateTimeField(read_only=True)

    class Meta:
        model  = TableToken
        fields = [
            'token', 'est_valide',
            'date_creation', 'date_derniere_utilisation',
        ]

    def get_est_valide(self, obj):
        return obj.est_valide()


# ─────────────────────────────────────────────────────────────────────────────
# SESSION TABLE
# ─────────────────────────────────────────────────────────────────────────────

class TableSessionSerializer(serializers.ModelSerializer):
    """Session de connexion QR d'une table."""
    table_login    = serializers.CharField(source='table.login', read_only=True)
    duree_secondes = serializers.SerializerMethodField()

    class Meta:
        model  = TableSession
        fields = [
            'id', 'table', 'table_login',
            'session_token',
            'date_creation', 'date_paiement',
            'est_active', 'duree_secondes',
        ]

    def get_duree_secondes(self, obj):
        """Secondes restantes avant expiration (si paiement effectué)."""
        if not obj.date_paiement or not obj.est_active:
            return None
        from django.utils import timezone
        from datetime import timedelta
        elapsed  = timezone.now() - obj.date_paiement
        restant  = timedelta(minutes=1) - elapsed
        secondes = int(restant.total_seconds())
        return max(0, secondes)