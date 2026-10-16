"""Idempotence des créations publiques via l'en-tête optionnel `Idempotency-Key`."""
import functools
import hashlib
import json

from django.db import IntegrityError, transaction
from drf_spectacular.utils import OpenApiParameter
from rest_framework import status
from rest_framework.response import Response

from .models import CleIdempotence

# À ajouter dans `parameters=[...]` de l'extend_schema des vues concernées
PARAMETRE_CLE_IDEMPOTENCE = OpenApiParameter(
    name='Idempotency-Key', location=OpenApiParameter.HEADER, required=False, type=str,
    description=(
        "Clé unique choisie par le client (128 caractères max). Renvoyer la même clé "
        "avec le même corps pendant 24 h rejoue la réponse d'origine sans rien recréer ; "
        "avec un corps différent, la requête est refusée (409)."
    ),
)


def idempotente(methode):
    """Décore le `post` d'une vue DRF. Sans en-tête : comportement inchangé.

    - Concurrence : la ligne de clé est créée dans une transaction qui reste ouverte
      pendant toute la vue ; une requête simultanée de même clé attend à l'insertion
      (contrainte d'unicité), puis relit la réponse mémorisée.
    - Seules les réponses 2xx sont mémorisées : une erreur (400, 404...) peut venir
      d'un état passager (plat indisponible) et ne doit pas être rejouée.
    """

    @functools.wraps(methode)
    def enveloppe(self, request, *args, **kwargs):
        cle = (request.headers.get('Idempotency-Key') or '').strip()
        if not cle:
            return methode(self, request, *args, **kwargs)
        if len(cle) > 128:
            return Response(
                {'success': False, 'message': "La clé d'idempotence est trop longue (128 caractères max).",
                 'errors': None},
                status=status.HTTP_400_BAD_REQUEST,
            )

        route = f"{request.method} {request.path}"
        corps = json.dumps(request.data, sort_keys=True, default=str, separators=(',', ':'))
        empreinte = hashlib.sha256(corps.encode('utf-8')).hexdigest()

        with transaction.atomic():
            try:
                with transaction.atomic():
                    enreg = CleIdempotence.objects.create(
                        cle=cle, utilisateur=request.user, route=route, empreinte=empreinte,
                    )
            except IntegrityError:
                enreg = CleIdempotence.objects.select_for_update().get(
                    cle=cle, utilisateur=request.user, route=route,
                )
                if enreg.empreinte != empreinte:
                    return Response(
                        {'success': False,
                         'message': "Cette demande a déjà été envoyée avec d'autres informations.",
                         'errors': None},
                        status=status.HTTP_409_CONFLICT,
                    )
                return Response(enreg.corps_reponse, status=enreg.code_reponse)

            reponse = methode(self, request, *args, **kwargs)
            if 200 <= reponse.status_code < 300:
                enreg.code_reponse = reponse.status_code
                enreg.corps_reponse = reponse.data
                enreg.save(update_fields=['code_reponse', 'corps_reponse'])
            else:
                enreg.delete()
            return reponse

    return enveloppe
