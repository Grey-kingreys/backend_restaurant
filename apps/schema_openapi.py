# apps/schema_openapi.py
# Briques communes de description OpenAPI (drf-spectacular) : enveloppe des réponses
# et format d'erreur. Utilisées uniquement par les décorateurs `extend_schema`,
# jamais à l'exécution des vues.

from drf_spectacular.utils import OpenApiResponse, PolymorphicProxySerializer, inline_serializer
from rest_framework import serializers


class ErreurSerializer(serializers.Serializer):
    """Format d'erreur unique de l'API (apps/accounts/exceptions.py et error_response)."""
    success = serializers.BooleanField(help_text="Toujours false pour une erreur.")
    errors = serializers.DictField(
        child=serializers.JSONField(), allow_null=True,
        help_text="Détail par champ ou par clé, null si l'erreur n'a pas de détail.",
    )
    message = serializers.CharField(help_text="Message lisible, affichable tel quel.")


def seulement_api_v1(endpoints):
    """Hook de prétraitement : seules les routes /api/v1/ sont décrites.
    Les routes /api/... historiques (web) restent servies mais ne sont pas
    dupliquées dans le schéma (operationId en collision)."""
    return [e for e in endpoints if e[0].startswith('/api/v1/')]


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


def donnees_paginables(nom, forme_complete, element, champs_en_plus=None):
    """`data` d'une liste à pagination optionnelle : soit la forme d'origine (sans `page`),
    soit `{count, suivant, precedent, resultats}` (avec `page`). Décrit en oneOf.

    `nom` : nom de composant unique ; `forme_complete` : instance de serializer de la forme
    d'origine ; `element` : instance de serializer (many=True) des éléments de `resultats` ;
    `champs_en_plus` : dict {nom: champ DRF} ajoutés à la forme paginée (ex. des statistiques)."""
    page = inline_serializer(name=f"{nom}Page", fields={
        'count': serializers.IntegerField(help_text="Nombre total d'éléments."),
        'suivant': serializers.URLField(allow_null=True, help_text="URL absolue de la page suivante, null si dernière page."),
        'precedent': serializers.URLField(allow_null=True, help_text="URL absolue de la page précédente, null si première page."),
        'resultats': element,
        **(champs_en_plus or {}),
    })
    return PolymorphicProxySerializer(
        component_name=nom, serializers=[forme_complete, page], resource_type_field_name=None,
    )


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
