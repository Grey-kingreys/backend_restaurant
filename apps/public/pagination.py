"""Pagination optionnelle des listes publiques : sans `?page=`, la réponse reste celle d'origine."""
from django.core.paginator import EmptyPage, Paginator
from drf_spectacular.utils import OpenApiParameter
from rest_framework import status
from rest_framework.response import Response

TAILLE_PAR_DEFAUT = 20
TAILLE_MAX = 50

# À ajouter dans `parameters=[...]` de l'extend_schema des listes concernées
PARAMETRES_PAGINATION = [
    OpenApiParameter(
        name='page', location=OpenApiParameter.QUERY, required=False, type=int,
        description=(
            "Numéro de page, à partir de 1. Sans ce paramètre, la liste complète est renvoyée "
            "(forme d'origine). Avec ce paramètre, `data` devient "
            "`{count, suivant, precedent, resultats}`."
        ),
    ),
    OpenApiParameter(
        name='taille', location=OpenApiParameter.QUERY, required=False, type=int,
        description=f"Éléments par page (1 à {TAILLE_MAX}, défaut {TAILLE_PAR_DEFAUT}). Utilisé avec `page`.",
    ),
]


def _erreur(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({'success': False, 'message': message, 'errors': None}, status=code)


def _entier(valeur):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


def paginer(request, elements, serialiser, en_plus=None):
    """Renvoie None si `page` est absent (l'appelant garde sa réponse d'origine), sinon
    la Response paginée. `elements` : queryset ordonné ; `serialiser(element)` : dict ;
    `en_plus()` : dict optionnel ajouté à `data` (calculé seulement si la page est valide)."""
    if 'page' not in request.query_params:
        return None

    numero = _entier(request.query_params.get('page'))
    if numero is None or numero < 1:
        return _erreur("Le numéro de page doit être un nombre entier supérieur ou égal à 1.")

    taille = TAILLE_PAR_DEFAUT
    if 'taille' in request.query_params:
        taille = _entier(request.query_params.get('taille'))
        if taille is None or not 1 <= taille <= TAILLE_MAX:
            return _erreur(f"La taille de page doit être un nombre entier entre 1 et {TAILLE_MAX}.")

    try:
        page = Paginator(elements, taille).page(numero)
    except EmptyPage:
        return _erreur("Cette page n'existe pas.", status.HTTP_404_NOT_FOUND)

    def lien(numero_page):
        parametres = request.query_params.copy()
        parametres['page'] = numero_page
        return f"{request.build_absolute_uri(request.path)}?{parametres.urlencode()}"

    return Response({
        'success': True,
        'data': {
            'count': page.paginator.count,
            'suivant': lien(page.next_page_number()) if page.has_next() else None,
            'precedent': lien(page.previous_page_number()) if page.has_previous() else None,
            'resultats': [serialiser(e) for e in page.object_list],
            **(en_plus() if en_plus else {}),
        },
        'message': "",
    })
