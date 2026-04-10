# apps/accounts/exceptions.py
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    """
    Handler global — uniformise toutes les erreurs DRF au format :
    { "success": false, "errors": {...}, "message": "..." }
    """
    response = exception_handler(exc, context)

    if response is not None:
        message_map = {
            400: "Données invalides.",
            401: "Authentification requise.",
            403: "Accès refusé.",
            404: "Ressource introuvable.",
            405: "Méthode non autorisée.",
            429: "Trop de requêtes. Veuillez patienter.",
            500: "Erreur serveur interne.",
        }
        message = message_map.get(response.status_code, "Une erreur est survenue.")

        # Extraire le détail si c'est un message simple
        data = response.data
        if isinstance(data, dict) and 'detail' in data:
            message = str(data['detail'])
            errors = None
        else:
            errors = data

        response.data = {
            "success": False,
            "errors": errors,
            "message": message,
        }

    return response