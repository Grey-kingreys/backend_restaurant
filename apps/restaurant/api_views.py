# apps/restaurant/api_views.py
"""
Phase 6 — Tables · QR Code · Sessions · Dashboard Serveur

Endpoints :
  GET/POST  /api/restaurant/tables/                    Admin/Serveur
  GET/PUT/PATCH/DELETE /api/restaurant/tables/<id>/    Admin
  GET       /api/restaurant/tables/<id>/qr/            Admin
  POST      /api/restaurant/tables/<id>/qr/generer/    Admin
  GET       /api/auth/qr/<token>/                      Public (dans accounts/api_views.py)

  GET       /api/restaurant/commandes/                 Serveur/Admin  (toutes commandes actives)
  POST      /api/restaurant/commandes/<id>/servie/     Serveur
  POST      /api/restaurant/commandes/<id>/payee/      Serveur

CDC §5.2 Serveur :
  - Tableau de bord tables en temps réel
  - Marquer une commande comme SERVIE
  - Valider le paiement → statut PAYÉE, transaction en attente de remise
  - Remettre l'argent physique au comptable désigné
  - Téléchargement du reçu PDF
"""
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

import base64
import uuid
import qrcode
from io import BytesIO

from apps.accounts.perm_codes import (
    PERM_VIEW_TABLES, PERM_MANAGE_TABLES,
    PERM_MANAGE_COMMANDES,
)
from .models import TableRestaurant, TableToken, TableSession
from .serializers import (
    TableRestaurantListSerializer,
    TableRestaurantDetailSerializer,
    TableRestaurantCreateSerializer,
    TableRestaurantUpdateSerializer,
    QRCodeInfoSerializer,
    TableSessionSerializer,
)


def ok(data=None, message="", code=status.HTTP_200_OK):
    return Response({"success": True, "data": data, "message": message}, status=code)


def err(errors=None, message="", code=status.HTTP_400_BAD_REQUEST):
    return Response({"success": False, "errors": errors, "message": message}, status=code)


# ─────────────────────────────────────────────────────────────────────────────
# TABLES — CRUD (Admin) / Lecture (Serveur)
# ─────────────────────────────────────────────────────────────────────────────

class TableListView(APIView):
    """
    GET  /api/restaurant/tables/  — Liste des tables du restaurant
    POST /api/restaurant/tables/  — Créer une table (Admin uniquement)

    CDC §5.6 Admin : CRUD tables physiques + génération QR Codes
    CDC §5.2 Serveur : tableau de bord tables en temps réel

    Filtres GET :
      ?statut=libre|en_attente|prete|servie
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Liste des tables du restaurant",
        description=(
            "Retourne toutes les tables du restaurant avec leur statut en temps réel.\n\n"
            "**Statuts possibles :** libre · en_attente · prete · servie\n\n"
            "Filtre optionnel : `?statut=libre|en_attente|prete|servie`\n\n"
            "**Accès :** Serveur, Chef Cuisinier, Admin, Manager"
        ),
        parameters=[
            OpenApiParameter('statut', OpenApiTypes.STR, description="Filtrer par statut", required=False),
        ],
        responses={
            200: TableRestaurantListSerializer(many=True),
            403: OpenApiResponse(description="Accès refusé"),
        },
        tags=["Tables"],
    )
    def get(self, request):
        if not request.user.has_permission(PERM_VIEW_TABLES):
            return err(message="Vous n'avez pas accès aux tables.", code=status.HTTP_403_FORBIDDEN)

        qs = TableRestaurant.objects.filter(
            utilisateur__restaurant=request.user.restaurant
        ).select_related('utilisateur').order_by('numero_table')

        # Filtre par statut (post-queryset car statut est calculé)
        statut_filter = request.query_params.get('statut')
        if statut_filter:
            from apps.commandes.models import Commande
            STATUTS_ACTIFS = ('en_attente', 'prete', 'servie')

            if statut_filter == 'libre':
                # Tables sans commande active
                tables_actives_ids = Commande.objects.filter(
                    statut__in=STATUTS_ACTIFS,
                    restaurant=request.user.restaurant
                ).values_list('table_id', flat=True)
                qs = qs.exclude(utilisateur_id__in=tables_actives_ids)

            elif statut_filter in STATUTS_ACTIFS:
                tables_avec_statut = Commande.objects.filter(
                    statut=statut_filter,
                    restaurant=request.user.restaurant
                ).values_list('table_id', flat=True)
                qs = qs.filter(utilisateur_id__in=tables_avec_statut)

        serializer = TableRestaurantListSerializer(qs, many=True)
        return ok(data={
            'count': qs.count(),
            'tables': serializer.data,
        })

    @extend_schema(
        summary="Créer une table physique",
        description=(
            "Crée une nouvelle table physique associée à un compte Rtable du restaurant.\n\n"
            "- Le compte Rtable doit appartenir au même restaurant\n"
            "- Un compte Rtable ne peut être associé qu'à une seule table\n"
            "- Le numéro de table doit être unique dans le restaurant\n\n"
            "**Accès :** Admin uniquement"
        ),
        request=TableRestaurantCreateSerializer,
        responses={
            201: TableRestaurantDetailSerializer,
            400: OpenApiResponse(description="Données invalides"),
            403: OpenApiResponse(description="Admin uniquement"),
        },
        tags=["Tables"],
    )
    def post(self, request):
        if not request.user.has_permission(PERM_MANAGE_TABLES):
            return err(message="Vous n'avez pas la permission de gérer les tables.", code=status.HTTP_403_FORBIDDEN)

        serializer = TableRestaurantCreateSerializer(
            data=request.data, context={'request': request}
        )
        if serializer.is_valid():
            table = serializer.save()
            return ok(
                data=TableRestaurantDetailSerializer(table, context={'request': request}).data,
                message=f"Table '{table.numero_table}' créée avec succès.",
                code=status.HTTP_201_CREATED,
            )
        return err(errors=serializer.errors, message="Données invalides.")


class TableDetailView(APIView):
    """
    GET    /api/restaurant/tables/<id>/  — Détail d'une table
    PUT    /api/restaurant/tables/<id>/  — Modifier une table (Admin)
    PATCH  /api/restaurant/tables/<id>/  — Modifier partiellement (Admin)
    DELETE /api/restaurant/tables/<id>/  — Supprimer une table (Admin)
    """
    permission_classes = [IsAuthenticated]

    def _get_table(self, request, pk):
        return get_object_or_404(
            TableRestaurant,
            pk=pk,
            utilisateur__restaurant=request.user.restaurant
        )

    @extend_schema(
        summary="Détail d'une table",
        description=(
            "Retourne le détail complet d'une table :\n"
            "commandes actives, session QR, statistiques.\n\n"
            "**Accès :** Serveur, Chef Cuisinier, Admin, Manager"
        ),
        responses={
            200: TableRestaurantDetailSerializer,
            403: OpenApiResponse(description="Accès refusé"),
            404: OpenApiResponse(description="Table non trouvée"),
        },
        tags=["Tables"],
    )
    def get(self, request, pk):
        if not request.user.has_permission(PERM_VIEW_TABLES):
            return err(message="Vous n'avez pas accès aux tables.", code=status.HTTP_403_FORBIDDEN)

        table = self._get_table(request, pk)
        return ok(data=TableRestaurantDetailSerializer(table, context={'request': request}).data)

    @extend_schema(
        summary="Modifier une table",
        request=TableRestaurantUpdateSerializer,
        responses={
            200: TableRestaurantDetailSerializer,
            400: OpenApiResponse(description="Données invalides"),
            403: OpenApiResponse(description="Admin uniquement"),
        },
        tags=["Tables"],
    )
    def put(self, request, pk):
        if not request.user.has_permission(PERM_MANAGE_TABLES):
            return err(message="Vous n'avez pas la permission de gérer les tables.", code=status.HTTP_403_FORBIDDEN)
        table = self._get_table(request, pk)
        s = TableRestaurantUpdateSerializer(
            table, data=request.data, context={'request': request}
        )
        if s.is_valid():
            table = s.save()
            return ok(
                data=TableRestaurantDetailSerializer(table, context={'request': request}).data,
                message=f"Table '{table.numero_table}' modifiée."
            )
        return err(errors=s.errors)

    @extend_schema(
        summary="Modifier partiellement une table",
        request=TableRestaurantUpdateSerializer,
        responses={
            200: TableRestaurantDetailSerializer,
            403: OpenApiResponse(description="Admin uniquement"),
        },
        tags=["Tables"],
    )
    def patch(self, request, pk):
        if not request.user.has_permission(PERM_MANAGE_TABLES):
            return err(message="Vous n'avez pas la permission de gérer les tables.", code=status.HTTP_403_FORBIDDEN)
        table = self._get_table(request, pk)
        s = TableRestaurantUpdateSerializer(
            table, data=request.data, partial=True, context={'request': request}
        )
        if s.is_valid():
            table = s.save()
            return ok(
                data=TableRestaurantDetailSerializer(table, context={'request': request}).data,
                message=f"Table '{table.numero_table}' modifiée."
            )
        return err(errors=s.errors)

    @extend_schema(
        summary="Supprimer une table",
        description=(
            "Supprime la table physique. Les commandes historiques sont conservées.\n\n"
            "**Accès :** Admin uniquement (CDC §5.6 / §10.5)"
        ),
        responses={
            200: OpenApiResponse(description="Table supprimée"),
            403: OpenApiResponse(description="Admin uniquement"),
            404: OpenApiResponse(description="Table non trouvée"),
        },
        tags=["Tables"],
    )
    def delete(self, request, pk):
        if not request.user.has_permission(PERM_MANAGE_TABLES):
            return err(message="Vous n'avez pas la permission de gérer les tables.", code=status.HTTP_403_FORBIDDEN)
        table = self._get_table(request, pk)
        numero = table.numero_table
        table.delete()
        return ok(message=f"Table '{numero}' supprimée.")


# ─────────────────────────────────────────────────────────────────────────────
# QR CODE
# ─────────────────────────────────────────────────────────────────────────────

class QRCodeInfoView(APIView):
    """
    GET /api/restaurant/tables/<id>/qr/
    Informations sur le QR Code d'une table (token, validité, dates).

    Accès : Admin uniquement
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Informations QR Code d'une table",
        description="Retourne les informations du QR Code de la table (validité, dates).\n\n**Accès :** Admin",
        responses={
            200: QRCodeInfoSerializer,
            403: OpenApiResponse(description="Admin uniquement"),
            404: OpenApiResponse(description="Table ou QR Code non trouvé"),
        },
        tags=["QR Code"],
    )
    def get(self, request, pk):
        if not request.user.has_permission(PERM_MANAGE_TABLES):
            return err(message="Vous n'avez pas la permission de gérer les tables.", code=status.HTTP_403_FORBIDDEN)

        table = get_object_or_404(
            TableRestaurant, pk=pk,
            utilisateur__restaurant=request.user.restaurant
        )

        try:
            token_obj = table.utilisateur.auth_token
        except TableToken.DoesNotExist:
            return ok(
                data={'a_qr_code': False},
                message="Aucun QR Code généré pour cette table."
            )

        # Rend l'image QR depuis le token existant — sans créer de nouveau token.
        qr_url = token_obj.get_qr_url(request)
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        qr_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        return ok(data={
            'qr_code_url': f"data:image/png;base64,{qr_b64}",
            'qr_login_url': qr_url,
            'table': table.numero_table,
            'a_qr_code': True,
        })


class QRCodeGenererView(APIView):
    """
    POST /api/restaurant/tables/<id>/qr/generer/
    Génère ou régénère le QR Code d'une table.
    Retourne l'image PNG directement (Content-Type: image/png).

    CDC §5.6 Admin : CRUD tables + génération QR Codes pour plastification

    Accès : Admin uniquement
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Générer / régénérer le QR Code d'une table",
        description=(
            "Génère un nouveau QR Code pour la table.\n\n"
            "- L'ancien token est remplacé → l'ancien QR Code ne fonctionne plus\n"
            "- Retourne l'image PNG directement (pour téléchargement / plastification)\n"
            "- Le QR Code encode l'URL de connexion automatique\n\n"
            "**Accès :** Admin uniquement"
        ),
        responses={
            200: OpenApiResponse(description="Image PNG du QR Code"),
            403: OpenApiResponse(description="Admin uniquement"),
            404: OpenApiResponse(description="Table non trouvée"),
        },
        tags=["QR Code"],
    )
    def post(self, request, pk):
        if not request.user.has_permission(PERM_MANAGE_TABLES):
            return err(message="Vous n'avez pas la permission de gérer les tables.", code=status.HTTP_403_FORBIDDEN)

        table_restaurant = get_object_or_404(
            TableRestaurant, pk=pk,
            utilisateur__restaurant=request.user.restaurant
        )
        table_user = table_restaurant.utilisateur

        # Générer ou régénérer le token
        token_obj = TableToken.generer_token(table_user)

        # Construire l'URL de connexion QR
        qr_url = token_obj.get_qr_url(request)

        # Générer l'image QR
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format='PNG')

        qr_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        return ok(data={
            'qr_code_url': f"data:image/png;base64,{qr_b64}",
            'qr_login_url': qr_url,
            'table': table_restaurant.numero_table,
        }, message=f"QR Code généré pour la table '{table_restaurant.numero_table}'.")


# ─────────────────────────────────────────────────────────────────────────────
# CONNEXION VIA QR CODE — Public
# ─────────────────────────────────────────────────────────────────────────────

class QRLoginView(APIView):
    """
    POST /api/auth/qr/<token>/
    Connexion automatique via QR Code avec validation GPS.

    - Vérifie token QR + distance GPS si restaurant configuré
    - Crée une session avec expires_at (duree_session_table du restaurant)
    - Retourne JWT tokens + session_token
    Accès : Public
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Connexion automatique via QR Code",
        description=(
            "Authentifie une table via QR Code.\n\n"
            "- Valide le token QR\n"
            "- Vérifie la position GPS si le restaurant a des coordonnées\n"
            "- Crée une session avec expiration\n\n"
            "**Accès :** Public"
        ),
        responses={
            200: OpenApiResponse(description="Tokens JWT + session_token"),
            400: OpenApiResponse(description="QR Code invalide, expiré ou hors zone"),
        },
        tags=["Authentification"],
    )
    def post(self, request, token):
        from rest_framework_simplejwt.tokens import RefreshToken
        from apps.accounts.serializers import UserMeSerializer
        from .models import haversine

        try:
            token_obj = TableToken.objects.select_related('table__restaurant').get(token=token)
        except TableToken.DoesNotExist:
            return err(message="QR Code invalide ou expiré.", code=status.HTTP_400_BAD_REQUEST)

        if not token_obj.est_valide():
            return err(
                message="Ce QR Code n'est plus valide — mot de passe modifié. Contactez l'administrateur.",
                code=status.HTTP_400_BAD_REQUEST
            )

        table = token_obj.table

        if not table.actif:
            return err(message="Ce compte table est désactivé.", code=status.HTTP_400_BAD_REQUEST)

        if table.restaurant and not table.restaurant.is_active:
            return err(message="Ce restaurant est suspendu.", code=status.HTTP_400_BAD_REQUEST)

        # Validation GPS si restaurant configuré
        restaurant = table.restaurant
        lat = request.data.get('lat')
        lng = request.data.get('lng')

        if restaurant and restaurant.latitude and restaurant.longitude:
            if lat is None or lng is None:
                return err(
                    message="Votre position GPS est requise pour vous connecter. Autorisez la géolocalisation.",
                    code=status.HTTP_400_BAD_REQUEST
                )
            try:
                dist = haversine(float(lat), float(lng), float(restaurant.latitude), float(restaurant.longitude))
            except (TypeError, ValueError):
                return err(message="Coordonnées GPS invalides.", code=status.HTTP_400_BAD_REQUEST)

            if dist > restaurant.rayon_connexion:
                dist_m = int(dist)
                return err(
                    message=f"Vous êtes à {dist_m} m du restaurant (max {restaurant.rayon_connexion} m). Vous devez être sur place pour vous connecter.",
                    code=status.HTTP_400_BAD_REQUEST
                )

        # Créer la session avec expiration
        duree = (restaurant.duree_session_table if restaurant else 60)
        expires_at = timezone.now() + timedelta(minutes=duree)

        session = TableSession.objects.create(
            table=table,
            django_session_key=str(uuid.uuid4()),
            expires_at=expires_at,
            lat_connexion=lat,
            lng_connexion=lng,
        )

        token_obj.marquer_utilise()
        refresh = RefreshToken.for_user(table)

        return ok(
            data={
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserMeSerializer(table).data,
                'session_token': str(session.session_token),
                'table_login': table.login,
                'restaurant': restaurant.nom if restaurant else None,
                'expires_at': expires_at.isoformat(),
            },
            message=f"Bienvenue ! Connecté en tant que {table.login}."
        )


# ─────────────────────────────────────────────────────────────────────────────
# SESSIONS TABLE
# ─────────────────────────────────────────────────────────────────────────────

class TableSessionListView(APIView):
    """
    GET /api/restaurant/sessions/
    Liste des sessions actives des tables du restaurant.

    Accès : Admin, Manager
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Sessions actives des tables",
        description="Liste les sessions QR actives. Accès : Admin, Manager.",
        responses={200: TableSessionSerializer(many=True)},
        tags=["Sessions"],
    )
    def get(self, request):
        if not request.user.has_permission(PERM_MANAGE_TABLES):
            return err(message="Vous n'avez pas accès aux sessions.", code=status.HTTP_403_FORBIDDEN)

        qs = TableSession.objects.filter(
            table__restaurant=request.user.restaurant,
            est_active=True
        ).select_related('table').order_by('-date_creation')

        return ok(data=TableSessionSerializer(qs, many=True).data)


# ─────────────────────────────────────────────────────────────────────────────
# CHECK POSITION — Vérification périodique GPS pour les tables
# ─────────────────────────────────────────────────────────────────────────────

class CheckPositionView(APIView):
    """
    POST /api/restaurant/tables/check-position/
    Vérification périodique de position GPS pour une session table active.

    Appelé toutes les 60s par le frontend Rtable.
    Retourne un statut qui pilote la déconnexion automatique.

    Statuts possibles :
    - ok            : tout va bien
    - out_of_range  : hors zone (3 échecs consécutifs → déconnecter)
    - expired_warn  : session expirée mais commandes en cours (avertir)
    - expired       : session expirée + tout payé (déclencher compte à rebours)
    - all_paid      : toutes commandes payées (déclencher compte à rebours)
    - no_session    : aucune session active

    Accès : Rtable authentifié uniquement
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Vérification position GPS table",
        tags=["Sessions"],
    )
    def post(self, request):
        from apps.commandes.models import Commande
        from .models import haversine

        if request.user.role != 'Rtable':
            return err(message="Réservé aux tables.", code=status.HTTP_403_FORBIDDEN)

        session = TableSession.objects.filter(
            table=request.user,
            est_active=True
        ).select_related('table__restaurant').order_by('-date_creation').first()

        if not session:
            return ok(data={'status': 'no_session'})

        restaurant = request.user.restaurant
        lat = request.data.get('lat')
        lng = request.data.get('lng')

        # 1. Vérification GPS (si restaurant configuré et coordonnées reçues)
        if lat is not None and lng is not None and restaurant and restaurant.latitude and restaurant.longitude:
            try:
                dist = haversine(float(lat), float(lng), float(restaurant.latitude), float(restaurant.longitude))
                if dist > restaurant.rayon_connexion:
                    strikes = session.incrementer_echec_gps()
                    if strikes >= 3:
                        session.expirer()
                        return ok(data={
                            'status': 'out_of_range',
                            'disconnect': True,
                            'message': f'Vous vous êtes éloigné du restaurant (>{restaurant.rayon_connexion} m).',
                        })
                    return ok(data={
                        'status': 'out_of_range',
                        'disconnect': False,
                        'strikes': strikes,
                        'message': f'Hors zone ({int(dist)} m). {3 - strikes} avertissement(s) avant déconnexion.',
                    })
                else:
                    session.reinitialiser_echecs_gps()
            except (TypeError, ValueError):
                pass
        elif lat is None or lng is None:
            # GPS indisponible — on tolère (ne pas incrémenter)
            pass

        # 2. Vérifier les commandes actives
        has_active_orders = Commande.objects.filter(
            user=request.user,
            statut__in=['en_attente', 'prete', 'servie']
        ).exists()

        # Détecter si toutes les commandes sont payées (et qu'il y en a eu)
        had_orders = Commande.objects.filter(user=request.user).exists()
        all_paid = had_orders and not has_active_orders

        if all_paid and not session.date_paiement:
            session.date_paiement = timezone.now()
            session.save(update_fields=['date_paiement'])

        # 3. Vérification expiration de session
        if session.expires_at and timezone.now() > session.expires_at:
            if has_active_orders:
                return ok(data={
                    'status': 'expired_warn',
                    'message': 'Votre session a expiré, mais vos commandes sont en cours de traitement.',
                })
            return ok(data={
                'status': 'expired',
                'message': 'Session expirée.',
                'paid_at': session.date_paiement.isoformat() if session.date_paiement else None,
            })

        # 4. Toutes les commandes payées → compte à rebours
        if all_paid:
            return ok(data={
                'status': 'all_paid',
                'paid_at': session.date_paiement.isoformat(),
                'message': 'Toutes vos commandes sont payées.',
            })

        # 5. Tout est OK
        minutes_remaining = None
        if session.expires_at:
            delta = session.expires_at - timezone.now()
            minutes_remaining = max(0, int(delta.total_seconds() / 60))

        return ok(data={
            'status': 'ok',
            'expires_at': session.expires_at.isoformat() if session.expires_at else None,
            'minutes_remaining': minutes_remaining,
        })


class CheckDistanceView(APIView):
    """
    POST /api/restaurant/tables/check-distance/

    Vérification de DISTANCE GPS pour une table connectée en login+password
    (sans session QR). Applique UNIQUEMENT la restriction de distance — pas
    d'expiration de session ni de déconnexion post-paiement (spécifiques au QR).

    Retourne { in_range: bool, distance?, message? }.
    Tolérant : si le restaurant n'a pas de coordonnées configurées ou si le GPS
    est indisponible, renvoie in_range=True (pas de blocage).
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Vérification distance table (login+password)", tags=["Sessions"])
    def post(self, request):
        from .models import haversine

        if request.user.role != 'Rtable':
            return err(message="Réservé aux tables.", code=status.HTTP_403_FORBIDDEN)

        restaurant = request.user.restaurant
        lat = request.data.get('lat')
        lng = request.data.get('lng')

        if not (restaurant and restaurant.latitude and restaurant.longitude) or lat is None or lng is None:
            return ok(data={'in_range': True})

        try:
            dist = haversine(float(lat), float(lng), float(restaurant.latitude), float(restaurant.longitude))
        except (TypeError, ValueError):
            return ok(data={'in_range': True})

        if dist > restaurant.rayon_connexion:
            return ok(data={
                'in_range': False,
                'distance': int(dist),
                'message': f"Vous devez être à moins de {restaurant.rayon_connexion} m du restaurant.",
            })
        return ok(data={'in_range': True, 'distance': int(dist)})


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD SERVEUR — Commandes actives par table
# CDC §5.2 Serveur : tableau de bord des tables en temps réel
# ─────────────────────────────────────────────────────────────────────────────

class ServeurDashboardView(APIView):
    """
    GET /api/restaurant/dashboard/serveur/
    Dashboard serveur : état de toutes les tables + commandes actives.

    Polling recommandé : toutes les 8 secondes (CDC plan migration Phase 6).
    Accès : Serveur, Admin, Manager
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Dashboard Serveur — état des tables en temps réel",
        description=(
            "Retourne l'état de toutes les tables du restaurant :\n"
            "- Statut : libre / en_attente / prete / servie\n"
            "- Commandes actives par table\n"
            "- Montant total en cours\n\n"
            "Polling recommandé : toutes les 8 secondes.\n\n"
            "**Accès :** Serveur, Admin, Manager"
        ),
        responses={
            200: OpenApiResponse(description="Dashboard serveur"),
            403: OpenApiResponse(description="Accès refusé"),
        },
        tags=["Serveur"],
    )
    def get(self, request):
        if not request.user.has_permission(PERM_VIEW_TABLES):
            return err(message="Vous n'avez pas accès au dashboard serveur.", code=status.HTTP_403_FORBIDDEN)

        from apps.commandes.models import Commande
        from apps.commandes.serializers import CommandeListSerializer

        tables = TableRestaurant.objects.filter(
            utilisateur__restaurant=request.user.restaurant
        ).select_related('utilisateur').order_by('numero_table')

        tables_data = []
        for table in tables:
            commandes_actives = Commande.objects.filter(
                table=table.utilisateur,
                statut__in=['en_attente', 'prete', 'servie']
            ).order_by('-date_commande')

            # Statut global de la table
            if not commandes_actives.exists():
                statut = 'libre'
            else:
                # Priorité : en_attente > prete > servie
                statuts = list(commandes_actives.values_list('statut', flat=True))
                if 'en_attente' in statuts:
                    statut = 'en_attente'
                elif 'prete' in statuts:
                    statut = 'prete'
                else:
                    statut = 'servie'

            tables_data.append({
                'table_id':       table.id,
                'numero_table':   table.numero_table,
                'nombre_places':  table.nombre_places,
                'table_login':    table.utilisateur.login,
                'statut':         statut,
                'nb_commandes_actives': commandes_actives.count(),
                'commandes': CommandeListSerializer(commandes_actives, many=True).data,
            })

        # Statistiques globales
        stats = {
            'total_tables':    len(tables_data),
            'libres':          sum(1 for t in tables_data if t['statut'] == 'libre'),
            'en_attente':      sum(1 for t in tables_data if t['statut'] == 'en_attente'),
            'pretes':          sum(1 for t in tables_data if t['statut'] == 'prete'),
            'servies':         sum(1 for t in tables_data if t['statut'] == 'servie'),
            'commandes_actives_total': sum(t['nb_commandes_actives'] for t in tables_data),
        }

        return ok(data={
            'tables': tables_data,
            'stats':  stats,
        })


# ─────────────────────────────────────────────────────────────────────────────
# COMMANDES SERVEUR — SERVIE & PAYÉE
# Ces endpoints dupliquent ceux de apps/commandes/api_views.py
# mais sont accessibles sous /api/restaurant/ pour la cohérence
# du dashboard serveur.
# ─────────────────────────────────────────────────────────────────────────────

class ServeurCommandeServieView(APIView):
    """
    POST /api/restaurant/commandes/<id>/servie/
    Alias serveur — marque une commande comme SERVIE.

    CDC §7.1 étape 4 — Serveur sert les plats.
    Accès : Serveur uniquement
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="[Serveur] Marquer une commande comme SERVIE",
        description=(
            "Le serveur marque la commande comme servie aux clients.\n\n"
            "Statut requis : PRÊTE (ou sans étape cuisine).\n\n"
            "CDC §7.1 étape 4. **Accès :** Serveur uniquement."
        ),
        responses={
            200: OpenApiResponse(description="Commande marquée SERVIE"),
            400: OpenApiResponse(description="Statut invalide"),
            403: OpenApiResponse(description="Serveur uniquement"),
            404: OpenApiResponse(description="Commande non trouvée"),
        },
        tags=["Serveur"],
    )
    def post(self, request, pk):
        from apps.commandes.models import Commande
        from apps.commandes.serializers import CommandeServieSerializer, CommandeDetailSerializer

        if not request.user.has_permission(PERM_MANAGE_COMMANDES):
            return err(message="Vous n'avez pas la permission de gérer les commandes.", code=status.HTTP_403_FORBIDDEN)

        commande = get_object_or_404(
            Commande, pk=pk, restaurant=request.user.restaurant
        )
        s = CommandeServieSerializer(data={}, context={'commande': commande})
        if s.is_valid():
            commande = s.save(serveur=request.user)
            return ok(
                data=CommandeDetailSerializer(commande, context={'request': request}).data,
                message=f"Commande #{commande.id} marquée SERVIE."
            )
        return err(errors=s.errors, message="Action impossible.")


class ServeurCommandePayeeView(APIView):
    """
    POST /api/restaurant/commandes/<id>/payee/
    Alias serveur — marque une commande comme PAYÉE.

    CDC §7.1 étape 5 — Serveur valide le paiement.
    Lance le countdown d'expiration de la session QR (1 min).
    Accès : Serveur uniquement
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="[Serveur] Marquer une commande comme PAYÉE",
        description=(
            "Le serveur valide le paiement physique.\n\n"
            "Statut requis : SERVIE.\n"
            "Déclenche l'expiration de la session QR dans 1 minute.\n\n"
            "CDC §7.1 étape 5. **Accès :** Serveur uniquement."
        ),
        responses={
            200: OpenApiResponse(description="Commande marquée PAYÉE"),
            400: OpenApiResponse(description="Statut invalide"),
            403: OpenApiResponse(description="Serveur uniquement"),
        },
        tags=["Serveur"],
    )
    def post(self, request, pk):
        from apps.commandes.models import Commande
        from apps.commandes.serializers import CommandePayeeSerializer, CommandeDetailSerializer

        if not request.user.has_permission(PERM_MANAGE_COMMANDES):
            return err(message="Vous n'avez pas la permission de gérer les commandes.", code=status.HTTP_403_FORBIDDEN)

        commande = get_object_or_404(
            Commande, pk=pk, restaurant=request.user.restaurant
        )
        s = CommandePayeeSerializer(data={}, context={'commande': commande})
        if s.is_valid():
            commande = s.save(serveur=request.user)
            return ok(
                data=CommandeDetailSerializer(commande, context={'request': request}).data,
                message=(
                    f"Commande #{commande.id} PAYÉE. "
                    "En attente de remise au comptable."
                )
            )
        return err(errors=s.errors, message="Action impossible.")

# ─────────────────────────────────────────────────────────────────────────────
# RÉSERVATIONS — Gestion staff (Admin / Manager / Serveur)
# ─────────────────────────────────────────────────────────────────────────────

from .models import Reservation as _Reservation
from .models import ReservationClientBloque as _ResaBloque
from .services.email_service import send_reservation_client as _email_resa_client


def _staff_resto_or_none(user):
    """Restaurant du membre staff, ou None si non autorisé (table/client/sans resto)."""
    if not user or not user.is_authenticated:
        return None
    if user.role in ('Rtable', 'Rclient', 'Rsuper_admin'):
        return None
    return user.restaurant


def _heure_fin_staff(heure, duree_minutes):
    from datetime import datetime, date, timedelta
    fin = datetime.combine(date.min, heure) + timedelta(minutes=int(duree_minutes or 120))
    return fin.strftime('%H:%M')


def _serialize_resa_staff(r, bloques_ids=None):
    no_show = _Reservation.no_show_count(r.client)
    bloque = (r.client_id in bloques_ids) if bloques_ids is not None else \
        _ResaBloque.objects.filter(restaurant=r.restaurant, client=r.client).exists()
    return {
        'id': r.id,
        'client_id': r.client_id,
        'table_numero': r.table.numero_table if r.table_id else None,
        'table_places': r.table.nombre_places if r.table_id else None,
        'client_nom': r.client.nom_complet or r.client.login,
        'client_telephone': r.client.telephone,
        'client_email': r.client.email,
        'date_reservation': r.date_reservation.isoformat(),
        'heure': r.heure.strftime('%H:%M'),
        'heure_fin': _heure_fin_staff(r.heure, r.duree_minutes),
        'duree_minutes': r.duree_minutes,
        'nombre_personnes': r.nombre_personnes,
        'note': r.note,
        'statut': r.statut,
        'statut_label': r.get_statut_display(),
        'no_show_count': no_show,
        'client_a_risque': no_show >= _Reservation.SEUIL_AVERTISSEMENT_NO_SHOW,
        'client_bloque': bloque,
        'date_creation': r.date_creation.isoformat(),
    }


class ReservationListView(APIView):
    """GET /api/restaurant/reservations/?statut= — réservations du restaurant (staff)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        resto = _staff_resto_or_none(request.user)
        if not resto:
            return err(message="Accès réservé au personnel du restaurant.", code=status.HTTP_403_FORBIDDEN)
        qs = _Reservation.objects.filter(restaurant=resto).select_related('client', 'table')
        statut = request.query_params.get('statut')
        if statut in dict(_Reservation.STATUT_CHOICES):
            qs = qs.filter(statut=statut)
        qs = qs.order_by('-date_reservation', '-heure')
        bloques_ids = set(
            _ResaBloque.objects.filter(restaurant=resto).values_list('client_id', flat=True)
        )
        rows = [_serialize_resa_staff(r, bloques_ids) for r in qs]
        return ok(data={'reservations': rows, 'count': len(rows)})


class ReservationConfirmerView(APIView):
    """POST /api/restaurant/reservations/<pk>/confirmer/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        resto = _staff_resto_or_none(request.user)
        if not resto:
            return err(message="Accès réservé au personnel du restaurant.", code=status.HTTP_403_FORBIDDEN)
        try:
            resa = _Reservation.objects.get(pk=pk, restaurant=resto)
        except _Reservation.DoesNotExist:
            return err(message="Réservation introuvable.", code=status.HTTP_404_NOT_FOUND)
        if resa.statut != 'en_attente':
            return err(message="Seule une réservation en attente peut être confirmée.")
        resa.statut = 'confirmee'
        resa.save(update_fields=['statut', 'date_modification'])
        try:
            _email_resa_client(resa)  # confirmation au client
        except Exception:
            pass
        return ok(data=_serialize_resa_staff(resa), message="Réservation confirmée.")


class ReservationRefuserView(APIView):
    """POST /api/restaurant/reservations/<pk>/refuser/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        resto = _staff_resto_or_none(request.user)
        if not resto:
            return err(message="Accès réservé au personnel du restaurant.", code=status.HTTP_403_FORBIDDEN)
        try:
            resa = _Reservation.objects.get(pk=pk, restaurant=resto)
        except _Reservation.DoesNotExist:
            return err(message="Réservation introuvable.", code=status.HTTP_404_NOT_FOUND)
        if resa.statut != 'en_attente':
            return err(message="Seule une réservation en attente peut être refusée.")
        resa.statut = 'refusee'
        resa.save(update_fields=['statut', 'date_modification'])
        return ok(data=_serialize_resa_staff(resa), message="Réservation refusée.")


def _get_resa_staff(user, pk):
    """(resto, resa) ou (resto, None) si introuvable ; (None, None) si non autorisé."""
    resto = _staff_resto_or_none(user)
    if not resto:
        return None, None
    try:
        return resto, _Reservation.objects.select_related('client', 'table').get(pk=pk, restaurant=resto)
    except _Reservation.DoesNotExist:
        return resto, None


class ReservationReaffecterView(APIView):
    """POST /api/restaurant/reservations/<pk>/reaffecter/ — body: table_id. Change la table attribuée."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        resto, resa = _get_resa_staff(request.user, pk)
        if not resto:
            return err(message="Accès réservé au personnel du restaurant.", code=status.HTTP_403_FORBIDDEN)
        if not resa:
            return err(message="Réservation introuvable.", code=status.HTTP_404_NOT_FOUND)
        if resa.statut not in ('en_attente', 'confirmee'):
            return err(message="Seule une réservation active peut être réaffectée.")
        try:
            table = TableRestaurant.objects.get(id=request.data.get('table_id'), restaurant=resto)
        except TableRestaurant.DoesNotExist:
            return err(message="Table introuvable.", code=status.HTTP_404_NOT_FOUND)
        if table.nombre_places < resa.nombre_personnes:
            return err(message=f"La table {table.numero_table} n'a que {table.nombre_places} place(s).")
        if not _Reservation.table_est_disponible(
            table, resa.date_reservation, resa.heure,
            duree_minutes=resa.duree_minutes, exclure_id=resa.id,
        ):
            return err(message=f"La table {table.numero_table} est déjà occupée sur ce créneau.")
        resa.table = table
        resa.save(update_fields=['table', 'date_modification'])
        return ok(data=_serialize_resa_staff(resa), message=f"Table réaffectée : {table.numero_table}.")


class ReservationTerminerView(APIView):
    """POST /api/restaurant/reservations/<pk>/terminer/ — le client est venu, service terminé."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        resto, resa = _get_resa_staff(request.user, pk)
        if not resto:
            return err(message="Accès réservé au personnel du restaurant.", code=status.HTTP_403_FORBIDDEN)
        if not resa:
            return err(message="Réservation introuvable.", code=status.HTTP_404_NOT_FOUND)
        if resa.statut not in ('en_attente', 'confirmee'):
            return err(message="Cette réservation n'est pas active.")
        resa.statut = 'terminee'
        resa.save(update_fields=['statut', 'date_modification'])
        return ok(data=_serialize_resa_staff(resa), message="Réservation marquée comme terminée.")


class ReservationNoShowView(APIView):
    """POST /api/restaurant/reservations/<pk>/no-show/ — le client n'est pas venu."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        resto, resa = _get_resa_staff(request.user, pk)
        if not resto:
            return err(message="Accès réservé au personnel du restaurant.", code=status.HTTP_403_FORBIDDEN)
        if not resa:
            return err(message="Réservation introuvable.", code=status.HTTP_404_NOT_FOUND)
        if resa.statut not in ('en_attente', 'confirmee'):
            return err(message="Cette réservation n'est pas active.")
        resa.statut = 'no_show'
        resa.save(update_fields=['statut', 'date_modification'])
        return ok(data=_serialize_resa_staff(resa), message="Client marqué absent (no-show).")


class ReservationBloquerClientView(APIView):
    """POST /api/restaurant/reservations/<pk>/bloquer-client/ — bloque le client du resto."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        resto, resa = _get_resa_staff(request.user, pk)
        if not resto:
            return err(message="Accès réservé au personnel du restaurant.", code=status.HTTP_403_FORBIDDEN)
        if not resa:
            return err(message="Réservation introuvable.", code=status.HTTP_404_NOT_FOUND)
        _ResaBloque.objects.get_or_create(
            restaurant=resto, client=resa.client,
            defaults={'raison': (request.data.get('raison') or '').strip()[:255]},
        )
        return ok(data=_serialize_resa_staff(resa), message="Client bloqué pour les réservations.")


class ReservationDebloquerClientView(APIView):
    """POST /api/restaurant/reservations/<pk>/debloquer-client/ — lève le blocage du client."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        resto, resa = _get_resa_staff(request.user, pk)
        if not resto:
            return err(message="Accès réservé au personnel du restaurant.", code=status.HTTP_403_FORBIDDEN)
        if not resa:
            return err(message="Réservation introuvable.", code=status.HTTP_404_NOT_FOUND)
        _ResaBloque.objects.filter(restaurant=resto, client=resa.client).delete()
        return ok(data=_serialize_resa_staff(resa), message="Client débloqué.")
