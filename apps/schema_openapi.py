# apps/schema_openapi.py
# Briques communes de description OpenAPI (drf-spectacular) : enveloppe des réponses
# et format d'erreur. Utilisées uniquement par les décorateurs `extend_schema`,
# jamais à l'exécution des vues.

from drf_spectacular.utils import OpenApiResponse, inline_serializer
from rest_framework import serializers


class ErreurSerializer(serializers.Serializer):
    """Format d'erreur unique de l'API (apps/accounts/exceptions.py et error_response)."""
    success = serializers.BooleanField(help_text="Toujours false pour une erreur.")
    errors = serializers.DictField(
        child=serializers.JSONField(), allow_null=True,
        help_text="Détail par champ ou par clé, null si l'erreur n'a pas de détail.",
    )
    message = serializers.CharField(help_text="Message lisible, affichable tel quel.")


DESCRIPTIONS_ERREURS = {
    400: "Données invalides.",
    401: "Authentification requise.",
    403: "Accès refusé.",
    404: "Ressource introuvable.",
    409: "Conflit avec l'état actuel de la ressource.",
    410: "Ressource expirée ou déjà utilisée.",
    429: "Trop de requêtes, réessayer plus tard.",
    500: "Erreur serveur interne.",
    502: "Service externe en échec.",
    503: "Service momentanément indisponible.",
}


def enveloppe(nom, data):
    """
    Décrit l'enveloppe de succès `{success, data, message}`.

    `data` : instance de serializer (avec `many=True` pour une liste) ou champ DRF.
    `nom` : nom de composant, unique sur toute l'API.
    """
    return inline_serializer(name=nom, fields={
        'success': serializers.BooleanField(help_text="Toujours true pour un succès."),
        'data': data,
        'message': serializers.CharField(help_text="Message lisible, peut être vide."),
    })


def enveloppe_sans_data(nom):
    """Enveloppe de succès dont `data` vaut toujours null (action qui ne renvoie qu'un message)."""
    return enveloppe(nom, serializers.CharField(
        allow_null=True, read_only=True, help_text="Toujours null pour cette opération.",
    ))


def erreurs(*codes):
    """Renvoie `{code: OpenApiResponse(ErreurSerializer, description)}` pour les codes demandés."""
    return {
        code: OpenApiResponse(ErreurSerializer, description=DESCRIPTIONS_ERREURS[code])
        for code in codes
    }
