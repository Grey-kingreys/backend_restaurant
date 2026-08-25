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
import re

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
    utilisateur_nom      = serializers.CharField(source='utilisateur.nom_complet', read_only=True)
    utilisateur_actif    = serializers.BooleanField(source='utilisateur.actif', read_only=True)
    statut_courant       = serializers.SerializerMethodField()
    a_qr_code            = serializers.SerializerMethodField()
    nb_commandes_actives = serializers.SerializerMethodField()

    class Meta:
        model  = TableRestaurant
        fields = [
            'id', 'numero_table', 'nombre_places',
            'utilisateur', 'utilisateur_login', 'utilisateur_nom', 'utilisateur_actif',
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
    utilisateur_nom   = serializers.CharField(source='utilisateur.nom_complet', read_only=True)
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
            'utilisateur', 'utilisateur_login', 'utilisateur_nom', 'utilisateur_actif',
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
    Création d'une table physique + compte Rtable en un seul appel.

    login et nom_complet servent à créer le User Rtable associé. Le mot de passe
    est optionnel : fourni → la table peut se connecter en login+password ;
    laissé vide → généré aléatoirement (connexion via QR code uniquement).
    """
    login       = serializers.CharField(write_only=True, max_length=50)
    nom_complet = serializers.CharField(write_only=True, max_length=150, required=False, allow_blank=True)
    password    = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model  = TableRestaurant
        fields = ['numero_table', 'nombre_places', 'login', 'nom_complet', 'password']

    def validate_password(self, value):
        if value and len(value) < 8:
            raise serializers.ValidationError("Le mot de passe doit contenir au moins 8 caractères.")
        return value

    def validate_login(self, value):
        """
        Le login saisi par l'admin n'a besoin d'être unique QUE dans son restaurant :
        deux restaurants peuvent tous les deux avoir une table « table_01 ».

        L'unicité globale exigée par `USERNAME_FIELD` est obtenue en préfixant
        automatiquement le login par le slug du restaurant — même convention que
        les comptes staff (`lebaobab_serveur_1`). Le préfixe n'est ajouté qu'une
        fois : un admin qui saisit déjà « lebaobab_table_01 » n'obtient pas
        « lebaobab_lebaobab_table_01 ».
        """
        restaurant = self.context['request'].user.restaurant
        if restaurant is None:
            raise serializers.ValidationError(
                "Votre compte n'est rattaché à aucun restaurant : impossible de créer une table."
            )

        # Normalisation : minuscules, espaces → « _ », caractères exotiques retirés,
        # puis nettoyage des « _ » redondants ou en bordure (« table-01 ! » → « table01 »).
        saisi = re.sub(r'[^a-z0-9_]', '', value.strip().lower().replace(' ', '_'))
        saisi = re.sub(r'_+', '_', saisi).strip('_')
        if not saisi:
            raise serializers.ValidationError("Le login ne peut pas être vide.")

        slug = restaurant.get_slug()
        prefixe = f"{slug}_"
        complet = saisi if saisi.startswith(prefixe) else f"{prefixe}{saisi}"

        max_len = User._meta.get_field('login').max_length
        if len(complet) > max_len:
            raise serializers.ValidationError(
                f"Login trop long : « {saisi} » ne doit pas dépasser "
                f"{max_len - len(prefixe)} caractères (le préfixe « {prefixe} » "
                "du restaurant est ajouté automatiquement)."
            )

        if User.objects.filter(login=complet).exists():
            raise serializers.ValidationError(
                f"Le login « {saisi} » est déjà utilisé dans ce restaurant. "
                "Choisissez-en un autre (un autre restaurant peut, lui, l'utiliser)."
            )
        return complet

    def validate_numero_table(self, value):
        request  = self.context['request']
        instance = self.instance
        qs = TableRestaurant.objects.filter(
            numero_table=value.strip().upper(),
            utilisateur__restaurant=request.user.restaurant,
        )
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"Le numéro de table « {value} » est déjà utilisé dans ce restaurant."
            )
        return value.strip().upper()

    def create(self, validated_data):
        import secrets
        restaurant  = self.context['request'].user.restaurant
        login       = validated_data.pop('login')
        num         = validated_data.get('numero_table', '')
        nom_complet = validated_data.pop('nom_complet', '').strip() or f"Table {num}"
        # Mot de passe fourni par l'admin (connexion manuelle) sinon aléatoire (QR only)
        password    = validated_data.pop('password', '').strip() or secrets.token_urlsafe(20)

        user = User.objects.create_user(
            login=login,
            role='Rtable',
            restaurant=restaurant,
            nom_complet=nom_complet,
            password=password,
            actif=True,
        )

        return TableRestaurant.objects.create(
            restaurant=restaurant,
            utilisateur=user,
            **validated_data,
        )


class TableRestaurantUpdateSerializer(serializers.ModelSerializer):
    """
    Modification partielle d'une table existante.
    Permet aussi de renommer le compte Rtable via nom_complet.
    Le login n'est jamais modifiable.
    """
    nom_complet = serializers.CharField(write_only=True, max_length=150, required=False, allow_blank=True)

    class Meta:
        model  = TableRestaurant
        fields = ['numero_table', 'nombre_places', 'nom_complet']

    def validate_numero_table(self, value):
        request  = self.context['request']
        instance = self.instance
        qs = TableRestaurant.objects.filter(
            numero_table=value.strip().upper(),
            utilisateur__restaurant=request.user.restaurant,
        )
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"Le numéro de table « {value} » est déjà utilisé dans ce restaurant."
            )
        return value.strip().upper()

    def update(self, instance, validated_data):
        nom_complet = validated_data.pop('nom_complet', None)
        if nom_complet is not None:
            # Champ vidé volontairement → on retombe sur le libellé par défaut
            # « Table <numéro> », jamais sur une chaîne vide.
            numero = validated_data.get('numero_table', instance.numero_table)
            instance.utilisateur.nom_complet = nom_complet.strip() or f"Table {numero}"
            instance.utilisateur.save(update_fields=['nom_complet'])
        return super().update(instance, validated_data)


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