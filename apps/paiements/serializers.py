# apps/paiements/serializers.py
from rest_framework import serializers
from django.db import transaction
from django.utils import timezone
from decimal import Decimal

from .models import (
    CaisseGenerale, CaisseGlobale, CaisseComptable,
    MouvementCaisse, RemiseServeur, Paiement, Depense,
)


# ─────────────────────────────────────────────────────────────────────────────
# CAISSE GENERALE
# ─────────────────────────────────────────────────────────────────────────────

class CaisseGeneraleSerializer(serializers.ModelSerializer):
    restaurant_nom = serializers.CharField(source='restaurant.nom', read_only=True)
    solde_formate  = serializers.SerializerMethodField()

    class Meta:
        model  = CaisseGenerale
        fields = [
            'id', 'restaurant', 'restaurant_nom',
            'solde', 'solde_formate', 'solde_initial',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_solde_formate(self, obj):
        return f"{obj.solde:,.0f} GNF".replace(',', ' ')


class CaisseGeneraleInitSerializer(serializers.Serializer):
    """Initialise le solde initial de la Caisse Generale (Admin uniquement)."""
    solde_initial = serializers.DecimalField(
        max_digits=14, decimal_places=2,
        min_value=Decimal('0.00'),
    )

    @transaction.atomic
    def save(self, caisse):
        solde = self.validated_data['solde_initial']
        caisse.solde_initial = solde
        caisse.solde = solde
        caisse.save(update_fields=['solde_initial', 'solde', 'updated_at'])
        return caisse


# ─────────────────────────────────────────────────────────────────────────────
# CAISSE GLOBALE
# ─────────────────────────────────────────────────────────────────────────────

class CaisseGlobaleSerializer(serializers.ModelSerializer):
    restaurant_nom = serializers.CharField(source='restaurant.nom', read_only=True)
    fermee_par_login = serializers.SerializerMethodField()
    solde_formate    = serializers.SerializerMethodField()
    statut           = serializers.SerializerMethodField()

    class Meta:
        model  = CaisseGlobale
        fields = [
            'id', 'restaurant', 'restaurant_nom',
            'date_ouverture', 'solde', 'solde_formate',
            'is_closed', 'statut', 'closed_at',
            'fermee_par', 'fermee_par_login',
            'montant_physique_fermeture', 'motif_ecart',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_fermee_par_login(self, obj):
        return obj.fermee_par.login if obj.fermee_par else None

    def get_solde_formate(self, obj):
        return f"{obj.solde:,.0f} GNF".replace(',', ' ')

    def get_statut(self, obj):
        return "fermee" if obj.is_closed else "ouverte"


class CaisseGlobaleFermerSerializer(serializers.Serializer):
    """Fermeture de la Caisse Globale par le comptable ou l'admin."""
    montant_physique = serializers.DecimalField(
        max_digits=14, decimal_places=2,
        min_value=Decimal('0.00'),
    )
    motif_ecart = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, data):
        caisse = self.context['caisse']
        if caisse.is_closed:
            raise serializers.ValidationError("Cette caisse est deja fermee.")

        montant = data['montant_physique']
        ecart   = abs(caisse.solde - montant)
        if ecart > 0 and not data.get('motif_ecart', '').strip():
            raise serializers.ValidationError({
                'motif_ecart': (
                    "Le motif est obligatoire si le montant physique "
                    "differe du solde virtuel."
                )
            })
        return data

    @transaction.atomic
    def save(self, fermee_par):
        caisse = self.context['caisse']
        return caisse.fermer(
            fermee_par=fermee_par,
            montant_physique=self.validated_data['montant_physique'],
            motif_ecart=self.validated_data.get('motif_ecart', '') or None,
        )


# ─────────────────────────────────────────────────────────────────────────────
# MOUVEMENT CAISSE
# ─────────────────────────────────────────────────────────────────────────────

class MouvementCaisseSerializer(serializers.ModelSerializer):
    effectue_par_login  = serializers.SerializerMethodField()
    type_mouvement_display = serializers.CharField(
        source='get_type_mouvement_display', read_only=True
    )
    montant_formate     = serializers.SerializerMethodField()

    class Meta:
        model  = MouvementCaisse
        fields = [
            'id', 'type_mouvement', 'type_mouvement_display',
            'montant', 'montant_formate', 'motif',
            'effectue_par', 'effectue_par_login',
            'created_at',
        ]
        read_only_fields = fields

    def get_effectue_par_login(self, obj):
        return obj.effectue_par.login if obj.effectue_par else None

    def get_montant_formate(self, obj):
        return f"{obj.montant:,.0f} GNF".replace(',', ' ')


# ─────────────────────────────────────────────────────────────────────────────
# CAISSE COMPTABLE
# ─────────────────────────────────────────────────────────────────────────────

class CaisseComptableSerializer(serializers.ModelSerializer):
    comptable_nom    = serializers.CharField(source='comptable.nom_complet', read_only=True)
    comptable_login  = serializers.CharField(source='comptable.login', read_only=True)
    restaurant_nom   = serializers.CharField(source='restaurant.nom', read_only=True)
    solde_formate    = serializers.SerializerMethodField()
    statut           = serializers.SerializerMethodField()
    mouvements       = MouvementCaisseSerializer(many=True, read_only=True)

    class Meta:
        model  = CaisseComptable
        fields = [
            'id', 'restaurant', 'restaurant_nom',
            'comptable', 'comptable_nom', 'comptable_login',
            'solde', 'solde_formate',
            'is_closed', 'statut',
            'opened_at', 'closed_at',
            'montant_physique_fermeture', 'motif_ecart',
            'mouvements',
        ]
        read_only_fields = fields

    def get_solde_formate(self, obj):
        return f"{obj.solde:,.0f} GNF".replace(',', ' ')

    def get_statut(self, obj):
        return "fermee" if obj.is_closed else "ouverte"


class CaisseComptableListSerializer(serializers.ModelSerializer):
    """Version allégée sans les mouvements — pour les listes."""
    comptable_nom   = serializers.CharField(source='comptable.nom_complet', read_only=True)
    comptable_login = serializers.CharField(source='comptable.login', read_only=True)
    solde_formate   = serializers.SerializerMethodField()
    statut          = serializers.SerializerMethodField()

    class Meta:
        model  = CaisseComptable
        fields = [
            'id', 'comptable', 'comptable_nom', 'comptable_login',
            'solde', 'solde_formate',
            'is_closed', 'statut',
            'opened_at', 'closed_at',
        ]
        read_only_fields = fields

    def get_solde_formate(self, obj):
        return f"{obj.solde:,.0f} GNF".replace(',', ' ')

    def get_statut(self, obj):
        return "fermee" if obj.is_closed else "ouverte"


class CaisseComptableOuvrirSerializer(serializers.Serializer):
    """Ouverture d'une nouvelle Caisse Comptable."""

    def validate(self, data):
        request = self.context['request']
        comptable = request.user
        # Verifier qu'il n'y a pas deja une caisse ouverte
        deja_ouverte = CaisseComptable.objects.filter(
            comptable=comptable,
            is_closed=False,
        ).exists()
        if deja_ouverte:
            raise serializers.ValidationError(
                "Vous avez deja une caisse ouverte. "
                "Fermez-la avant d'en ouvrir une nouvelle."
            )
        return data

    @transaction.atomic
    def save(self):
        request = self.context['request']
        return CaisseComptable.objects.create(
            restaurant=request.user.restaurant,
            comptable=request.user,
            solde=Decimal('0.00'),
        )


class ApprovisionnerSerializer(serializers.Serializer):
    """
    Approvisionnement de la Caisse Comptable depuis la Caisse Generale.
    Debite la Caisse Generale et credite la Caisse Comptable.
    """
    montant = serializers.DecimalField(
        max_digits=14, decimal_places=2,
        min_value=Decimal('0.01'),
    )
    motif = serializers.CharField(max_length=255, min_length=5)

    def validate_montant(self, value):
        caisse_comptable = self.context['caisse']
        caisse_generale  = caisse_comptable.restaurant.caisse_generale
        if not caisse_generale.peut_debiter(value):
            raise serializers.ValidationError(
                f"Solde insuffisant dans la Caisse Generale : "
                f"{caisse_generale.solde:,.0f} GNF disponibles.".replace(',', ' ')
            )
        return value

    def validate(self, data):
        caisse = self.context['caisse']
        if caisse.is_closed:
            raise serializers.ValidationError(
                "Impossible d'approvisionner une caisse fermee."
            )
        return data

    @transaction.atomic
    def save(self, effectue_par):
        caisse   = self.context['caisse']
        montant  = self.validated_data['montant']
        motif    = self.validated_data['motif']

        # Debiter la Caisse Generale
        caisse.restaurant.caisse_generale.debiter(montant)

        # Crediter la Caisse Comptable
        caisse.crediter(montant)

        # Tracer le mouvement
        MouvementCaisse.objects.create(
            caisse_comptable=caisse,
            type_mouvement='approvisionnement',
            montant=montant,
            motif=motif,
            effectue_par=effectue_par,
        )
        return caisse


class DepenseCreateSerializer(serializers.Serializer):
    """
    Enregistrement d'une depense depuis la Caisse Comptable.
    Verifie que le solde est suffisant avant de debiter.
    """
    motif       = serializers.CharField(max_length=255, min_length=5)
    montant     = serializers.DecimalField(
        max_digits=10, decimal_places=2,
        min_value=Decimal('0.01'),
    )
    date_depense = serializers.DateField()

    def validate_montant(self, value):
        caisse = self.context['caisse']
        if not caisse.peut_effectuer_depense(value):
            raise serializers.ValidationError(
                f"Solde insuffisant : {caisse.solde:,.0f} GNF disponibles.".replace(',', ' ')
            )
        return value

    def validate(self, data):
        caisse = self.context['caisse']
        if caisse.is_closed:
            raise serializers.ValidationError(
                "Impossible d'enregistrer une depense sur une caisse fermee."
            )
        return data

    @transaction.atomic
    def save(self, enregistree_par):
        caisse  = self.context['caisse']
        montant = self.validated_data['montant']

        # Debiter la caisse
        caisse.debiter(montant)

        # Creer la depense
        depense = Depense.objects.create(
            caisse_comptable=caisse,
            motif=self.validated_data['motif'],
            montant=montant,
            date_depense=self.validated_data['date_depense'],
            enregistree_par=enregistree_par,
        )

        # Tracer le mouvement
        MouvementCaisse.objects.create(
            caisse_comptable=caisse,
            type_mouvement='depense',
            montant=montant,
            motif=self.validated_data['motif'],
            effectue_par=enregistree_par,
        )
        return depense


class CaisseComptableFermerSerializer(serializers.Serializer):
    """Fermeture de la Caisse Comptable avec reconciliation physique."""
    montant_physique = serializers.DecimalField(
        max_digits=14, decimal_places=2,
        min_value=Decimal('0.00'),
    )
    motif_ecart = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, data):
        caisse  = self.context['caisse']
        if caisse.is_closed:
            raise serializers.ValidationError("Cette caisse est deja fermee.")

        montant = data['montant_physique']
        ecart   = abs(caisse.solde - montant)
        if ecart > 0 and not data.get('motif_ecart', '').strip():
            raise serializers.ValidationError({
                'motif_ecart': (
                    "Le motif est obligatoire si le montant physique "
                    "differe du solde virtuel."
                )
            })
        return data

    @transaction.atomic
    def save(self):
        caisse = self.context['caisse']
        return caisse.fermer(
            montant_physique=self.validated_data['montant_physique'],
            motif_ecart=self.validated_data.get('motif_ecart', '') or None,
        )


# ─────────────────────────────────────────────────────────────────────────────
# DEPENSE
# ─────────────────────────────────────────────────────────────────────────────

class DepenseSerializer(serializers.ModelSerializer):
    enregistree_par_login = serializers.SerializerMethodField()
    montant_formate       = serializers.SerializerMethodField()

    class Meta:
        model  = Depense
        fields = [
            'id', 'caisse_comptable', 'motif', 'montant', 'montant_formate',
            'date_depense', 'date_enregistrement',
            'enregistree_par', 'enregistree_par_login',
        ]
        read_only_fields = fields

    def get_enregistree_par_login(self, obj):
        return obj.enregistree_par.login if obj.enregistree_par else None

    def get_montant_formate(self, obj):
        return f"{obj.montant:,.0f} GNF".replace(',', ' ')


# ─────────────────────────────────────────────────────────────────────────────
# PAIEMENT
# ─────────────────────────────────────────────────────────────────────────────

class PaiementSerializer(serializers.ModelSerializer):
    commande_table_login = serializers.SerializerMethodField()
    montant_formate      = serializers.SerializerMethodField()
    remise_validee       = serializers.SerializerMethodField()

    class Meta:
        model  = Paiement
        fields = [
            'id', 'commande', 'commande_table_login',
            'montant', 'montant_formate',
            'date_paiement', 'remise_validee',
        ]
        read_only_fields = fields

    def get_commande_table_login(self, obj):
        return obj.commande.table.login

    def get_montant_formate(self, obj):
        return f"{obj.montant:,.0f} GNF".replace(',', ' ')

    def get_remise_validee(self, obj):
        try:
            return obj.remise.valide
        except Exception:
            return None


# ─────────────────────────────────────────────────────────────────────────────
# REMISE SERVEUR
# ─────────────────────────────────────────────────────────────────────────────

class RemiseServeurSerializer(serializers.ModelSerializer):
    serveur_login      = serializers.SerializerMethodField()
    validee_par_login  = serializers.SerializerMethodField()
    montant_virtuel_formate  = serializers.SerializerMethodField()
    montant_physique_formate = serializers.SerializerMethodField()
    ecart_formate      = serializers.SerializerMethodField()
    statut             = serializers.SerializerMethodField()
    commande_id        = serializers.IntegerField(source='paiement.commande_id', read_only=True)

    class Meta:
        model  = RemiseServeur
        fields = [
            'id', 'caisse_globale', 'paiement', 'commande_id',
            'serveur', 'serveur_login',
            'montant_virtuel', 'montant_virtuel_formate',
            'montant_physique', 'montant_physique_formate',
            'motif_ecart', 'ecart_formate',
            'valide', 'statut',
            'validee_par', 'validee_par_login',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_serveur_login(self, obj):
        return obj.serveur.login if obj.serveur else None

    def get_validee_par_login(self, obj):
        return obj.validee_par.login if obj.validee_par else None

    def get_montant_virtuel_formate(self, obj):
        return f"{obj.montant_virtuel:,.0f} GNF".replace(',', ' ')

    def get_montant_physique_formate(self, obj):
        if obj.montant_physique is not None:
            return f"{obj.montant_physique:,.0f} GNF".replace(',', ' ')
        return None

    def get_ecart_formate(self, obj):
        e = obj.ecart
        if e is not None:
            return f"{e:,.0f} GNF".replace(',', ' ')
        return None

    def get_statut(self, obj):
        if obj.valide:
            return "validee"
        if obj.montant_physique is not None:
            return "en_attente_validation"
        return "en_attente_remise"


class RemiseValiderSerializer(serializers.Serializer):
    """
    Validation physique d'une remise par le comptable.
    Le comptable saisit le montant physique recu et valide.
    Si ecart -> motif obligatoire.
    La Caisse Globale est creditee a la validation.
    """
    montant_physique = serializers.DecimalField(
        max_digits=14, decimal_places=2,
        min_value=Decimal('0.00'),
    )
    motif_ecart = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, data):
        remise = self.context['remise']

        if remise.valide:
            raise serializers.ValidationError("Cette remise a deja ete validee.")

        montant_virtuel = remise.montant_virtuel
        montant_physique = data['montant_physique']
        ecart = abs(montant_virtuel - montant_physique)

        if ecart > 0 and not data.get('motif_ecart', '').strip():
            raise serializers.ValidationError({
                'motif_ecart': (
                    "Le motif d'ecart est obligatoire si le montant "
                    "physique differe du montant virtuel."
                )
            })
        return data

    @transaction.atomic
    def save(self, validee_par):
        remise  = self.context['remise']
        montant = self.validated_data['montant_physique']
        motif   = self.validated_data.get('motif_ecart', '') or None

        remise.montant_physique = montant
        remise.motif_ecart      = motif
        remise.valide           = True
        remise.validee_par      = validee_par
        remise.save()

        # Crediter la Caisse Globale avec le montant physique recu
        remise.caisse_globale.crediter(montant)
        return remise


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD COMPTABLE
# ─────────────────────────────────────────────────────────────────────────────

class DashboardComptableSerializer(serializers.Serializer):
    """Stats du dashboard pour le comptable."""
    caisse_globale_active      = CaisseGlobaleSerializer(allow_null=True)
    ma_caisse_comptable        = CaisseComptableListSerializer(allow_null=True)
    remises_en_attente_count   = serializers.IntegerField()
    remises_validees_today     = serializers.IntegerField()
    total_remises_today        = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_depenses_today       = serializers.DecimalField(max_digits=14, decimal_places=2)
