"""
Rejet explicite des champs inconnus dans les serialiseurs d'ecriture.

Par defaut, DRF **ignore silencieusement** toute cle absente des `fields` du
serialiseur : la requete passe en 200/201 et la valeur est perdue sans le
moindre message. C'est ce qui s'etait produit avec `solde_initial` sur la
creation d'un restaurant — le Super Admin saisissait un montant, l'API
repondait « cree avec succes », et le coffre restait a 0 GNF.

Ce mixin transforme ce silence en erreur 400 lisible, cote appelant.

Ne sont refusees que les cles totalement absentes de `self.fields`. Les champs
en lecture seule (`id`, `created_at`...) restent acceptes et ignores comme
avant : un client qui renvoie l'objet complet en PATCH continue de fonctionner.
"""

from rest_framework import serializers


class RejetteChampsInconnusMixin:
    """
    A placer AVANT la classe de base : `class X(RejetteChampsInconnusMixin,
    serializers.ModelSerializer)`, pour que son `to_internal_value` s'execute.
    """

    def to_internal_value(self, data):
        if isinstance(data, dict):
            inconnus = sorted(set(data) - set(self.fields))
            if inconnus:
                raise serializers.ValidationError({
                    champ: "Champ inconnu pour cette ressource."
                    for champ in inconnus
                })
        return super().to_internal_value(data)


class SerializerStrict(RejetteChampsInconnusMixin, serializers.Serializer):
    """`serializers.Serializer` refusant les champs inconnus."""


class ModelSerializerStrict(RejetteChampsInconnusMixin, serializers.ModelSerializer):
    """`serializers.ModelSerializer` refusant les champs inconnus."""
