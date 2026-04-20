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
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

import qrcode
from io import BytesIO

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
        if not any(getattr(request.user, r)() for r in (
            'is_serveur', 'is_chef_cuisinier', 'is_admin', 'is_manager'
        )):
            return err(message="Accès refusé.", code=status.HTTP_403_FORBIDDEN)

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
        if not request.user.is_admin():
            return err(message="Seul l'Admin peut créer des tables.", code=status.HTTP_403_FORBIDDEN)

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
        if not any(getattr(request.user, r)() for r in (
            'is_serveur', 'is_chef_cuisinier', 'is_admin', 'is_manager'
        )):
            return err(message="Accès refusé.", code=status.HTTP_403_FORBIDDEN)

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
        if not request.user.is_admin():
            return err(message="Admin uniquement.", code=status.HTTP_403_FORBIDDEN)
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
        if not request.user.is_admin():
            return err(message="Admin uniquement.", code=status.HTTP_403_FORBIDDEN)
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
        if not request.user.is_admin():
            return err(message="Admin uniquement.", code=status.HTTP_403_FORBIDDEN)
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
        if not request.user.is_admin():
            return err(message="Admin uniquement.", code=status.HTTP_403_FORBIDDEN)

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

        return ok(data=QRCodeInfoSerializer(token_obj).data)


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
        if not request.user.is_admin():
            return err(message="Admin uniquement.", code=status.HTTP_403_FORBIDDEN)

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
        buffer.seek(0)

        filename = f"qr_table_{table_restaurant.numero_table}.png"
        response = HttpResponse(buffer, content_type='image/png')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['X-QR-URL']   = qr_url
        response['X-QR-Token'] = token_obj.token
        return response


# ─────────────────────────────────────────────────────────────────────────────
# CONNEXION VIA QR CODE — Public
# ─────────────────────────────────────────────────────────────────────────────

class QRLoginView(APIView):
    """
    GET /api/auth/qr/<token>/
    Connexion automatique via QR Code.

    CDC §7.2 QR Code et session Table :
    - QR Code unique par table, généré par l'Admin
    - Au scan → connexion automatique + génération d'un nouveau token de session
    - Token invalidé si le mot de passe de la table change
    - Session expire 1 minute après que toutes les commandes de la session sont PAYÉES

    Retourne les JWT tokens (access + refresh) pour la connexion frontend.
    Accès : Public (pas d'authentification requise)
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Connexion automatique via QR Code",
        description=(
            "Authentifie automatiquement une table via son QR Code.\n\n"
            "- Vérifie que le token QR est valide (mot de passe non modifié)\n"
            "- Crée une nouvelle session de table\n"
            "- Retourne les tokens JWT (access + refresh)\n"
            "- Le frontend stocke `session_token` pour l'isolation des commandes\n\n"
            "**Accès :** Public"
        ),
        responses={
            200: OpenApiResponse(description="Tokens JWT + session_token"),
            400: OpenApiResponse(description="QR Code invalide ou expiré"),
        },
        tags=["Authentification"],
    )
    def get(self, request, token):
        # Récupérer le token QR
        try:
            token_obj = TableToken.objects.select_related('table').get(token=token)
        except TableToken.DoesNotExist:
            return err(
                message="QR Code invalide ou expiré.",
                code=status.HTTP_400_BAD_REQUEST
            )

        # Vérifier la validité (mot de passe non modifié)
        if not token_obj.est_valide():
            return err(
                message=(
                    "Ce QR Code n'est plus valide — le mot de passe de la table a été modifié. "
                    "Contactez l'administrateur pour générer un nouveau QR Code."
                ),
                code=status.HTTP_400_BAD_REQUEST
            )

        table = token_obj.table

        # Vérifier que la table est active
        if not table.actif:
            return err(
                message="Ce compte table est désactivé.",
                code=status.HTTP_400_BAD_REQUEST
            )

        # Vérifier que le restaurant est actif
        if table.restaurant and not table.restaurant.is_active:
            return err(
                message="Ce restaurant est suspendu.",
                code=status.HTTP_400_BAD_REQUEST
            )

        # Générer les tokens JWT
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(table)

        # Créer une nouvelle session de table
        # La clé de session Django n'existe pas en mode API, on utilise le token JWT
        session = TableSession.objects.create(
            table=table,
            django_session_key=str(refresh.access_token)[:40],  # Tronqué pour contrainte unique
        )

        # Marquer le token comme utilisé
        token_obj.marquer_utilise()

        return ok(
            data={
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'session_token': str(session.session_token),
                'table_login': table.login,
                'restaurant': table.restaurant.nom if table.restaurant else None,
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
        if not any(getattr(request.user, r)() for r in ('is_admin', 'is_manager')):
            return err(message="Accès refusé.", code=status.HTTP_403_FORBIDDEN)

        qs = TableSession.objects.filter(
            table__restaurant=request.user.restaurant,
            est_active=True
        ).select_related('table').order_by('-date_creation')

        return ok(data=TableSessionSerializer(qs, many=True).data)


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
        if not any(getattr(request.user, r)() for r in (
            'is_serveur', 'is_admin', 'is_manager'
        )):
            return err(message="Accès refusé.", code=status.HTTP_403_FORBIDDEN)

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

        if not request.user.is_serveur():
            return err(message="Accès réservé aux Serveurs.", code=status.HTTP_403_FORBIDDEN)

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

        if not request.user.is_serveur():
            return err(message="Accès réservé aux Serveurs.", code=status.HTTP_403_FORBIDDEN)

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