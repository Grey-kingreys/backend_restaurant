# apps/commandes/api_views.py
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import Commande, PanierItem
from .serializers import (
    PanierItemSerializer,
    PanierItemCreateSerializer,
    CommandeListSerializer,
    CommandeDetailSerializer,
    CommandeValiderSerializer,
    CommandeCuisinierSerializer,
    CommandePreteSerializer,
    CommandeServieSerializer,
    CommandePayeeSerializer,
)
from .pdf_utils import generer_recu_pdf


def ok(data=None, message="", code=status.HTTP_200_OK):
    return Response({"success": True, "data": data, "message": message}, status=code)


def err(errors=None, message="", code=status.HTTP_400_BAD_REQUEST):
    return Response({"success": False, "errors": errors, "message": message}, status=code)


def _session_active(request):
    from apps.restaurant.models import TableSession
    try:
        return TableSession.objects.get(table=request.user, est_active=True)
    except TableSession.DoesNotExist:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# PANIER — Table uniquement
# ─────────────────────────────────────────────────────────────────────────────

class PanierView(APIView):
    permission_classes = [IsAuthenticated]

    def _require_table(self, request):
        if not request.user.is_table():
            return err(message="Accès réservé aux Tables.", code=status.HTTP_403_FORBIDDEN)
        return None

    @extend_schema(
        summary="Voir le panier",
        description="Retourne les items du panier, le nombre d'articles et le montant total. Accès : Table uniquement.",
        responses={200: PanierItemSerializer, 403: OpenApiResponse(description="Accès réservé aux Tables")},
        tags=["Panier"],
    )
    def get(self, request):
        if e := self._require_table(request):
            return e
        items = PanierItem.objects.filter(table=request.user).select_related('plat').order_by('date_ajout')
        montant_total = sum(i.sous_total for i in items)
        return ok(data={
            'items': PanierItemSerializer(items, many=True, context={'request': request}).data,
            'nb_items': items.count(),
            'montant_total': str(montant_total),
        })

    @extend_schema(
        summary="Ajouter ou mettre à jour un plat dans le panier",
        description="Ajoute un plat au panier ou met à jour sa quantité. Accès : Table uniquement.",
        request=PanierItemCreateSerializer,
        responses={200: PanierItemSerializer, 400: OpenApiResponse(description="Données invalides"), 403: OpenApiResponse(description="Accès réservé aux Tables")},
        tags=["Panier"],
    )
    def post(self, request):
        if e := self._require_table(request):
            return e
        s = PanierItemCreateSerializer(data=request.data, context={'request': request})
        if s.is_valid():
            item = s.save_to_panier(request.user)
            return ok(
                data=PanierItemSerializer(item, context={'request': request}).data,
                message=f"« {item.plat.nom} » ajouté au panier.",
            )
        return err(errors=s.errors, message="Données invalides.")

    @extend_schema(
        summary="Vider le panier",
        description="Supprime tous les items du panier. Accès : Table uniquement.",
        responses={200: OpenApiResponse(description="Panier vidé"), 403: OpenApiResponse(description="Accès réservé aux Tables")},
        tags=["Panier"],
    )
    def delete(self, request):
        if e := self._require_table(request):
            return e
        count, _ = PanierItem.objects.filter(table=request.user).delete()
        return ok(data={'supprimés': count}, message="Panier vidé.")


class PanierItemView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Retirer un plat du panier",
        description="Supprime un plat spécifique du panier. Accès : Table uniquement.",
        responses={
            200: OpenApiResponse(description="Plat retiré"),
            403: OpenApiResponse(description="Accès réservé aux Tables"),
            404: OpenApiResponse(description="Plat non trouvé dans le panier"),
        },
        tags=["Panier"],
    )
    def delete(self, request, plat_id):
        if not request.user.is_table():
            return err(message="Accès réservé aux Tables.", code=status.HTTP_403_FORBIDDEN)
        item = get_object_or_404(PanierItem, table=request.user, plat_id=plat_id)
        nom  = item.plat.nom
        item.delete()
        return ok(message=f"« {nom} » retiré du panier.")


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION COMMANDE — Table uniquement
# ─────────────────────────────────────────────────────────────────────────────

class CommandeValiderView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Valider le panier → créer une commande EN_ATTENTE",
        description="Transforme le panier en commande liée à la session QR active. Le panier est vidé. Accès : Table uniquement.",
        responses={
            201: CommandeDetailSerializer,
            400: OpenApiResponse(description="Panier vide ou plats indisponibles"),
            403: OpenApiResponse(description="Accès réservé aux Tables"),
        },
        tags=["Commandes"],
    )
    def post(self, request):
        if not request.user.is_table():
            return err(message="Accès réservé aux Tables.", code=status.HTTP_403_FORBIDDEN)
        s = CommandeValiderSerializer(data={}, context={'request': request})
        if s.is_valid():
            commande = s.create()
            return ok(
                data=CommandeDetailSerializer(commande, context={'request': request}).data,
                message=f"Commande #{commande.id} créée. Montant : {commande.montant_total} GNF.",
                code=status.HTTP_201_CREATED,
            )
        return err(errors=s.errors, message="Validation échouée.")


# ─────────────────────────────────────────────────────────────────────────────
# MES COMMANDES — Table (isolation session QR)
# ─────────────────────────────────────────────────────────────────────────────

class MesCommandesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Mes commandes (session courante)",
        description="Retourne les commandes de la table connectée filtrées par session QR courante. Accès : Table uniquement.",
        responses={
            200: CommandeListSerializer(many=True),
            403: OpenApiResponse(description="Accès réservé aux Tables"),
        },
        tags=["Commandes"],
    )
    def get(self, request):
        if not request.user.is_table():
            return err(message="Accès réservé aux Tables.", code=status.HTTP_403_FORBIDDEN)

        session = _session_active(request)

        if session:
            qs = Commande.objects.filter(
                table=request.user,
                restaurant=request.user.restaurant,
                session=session,
            ).order_by('-date_commande')
        else:
            qs = Commande.objects.filter(
                table=request.user,
                restaurant=request.user.restaurant,
                session__isnull=True,
            ).order_by('-date_commande')

        return ok(data={
            'count': qs.count(),
            'commandes': CommandeListSerializer(qs, many=True).data,
        })


# ─────────────────────────────────────────────────────────────────────────────
# TOUTES LES COMMANDES — Serveur, Chef Cuisinier, Admin, Manager
# ─────────────────────────────────────────────────────────────────────────────

class AllCommandesView(APIView):
    permission_classes = [IsAuthenticated]

    ROLES_AUTORISES = ('is_serveur', 'is_chef_cuisinier', 'is_admin', 'is_manager')

    def _check_access(self, user):
        return any(getattr(user, r)() for r in self.ROLES_AUTORISES)

    @extend_schema(
        summary="Toutes les commandes du restaurant",
        description="Retourne toutes les commandes du restaurant. Filtres : statut, table_id. Accès : Serveur, Chef Cuisinier, Admin, Manager.",
        parameters=[
            OpenApiParameter('statut', OpenApiTypes.STR, description="en_attente | prete | servie | payee", required=False),
            OpenApiParameter('table_id', OpenApiTypes.INT, description="ID de la table", required=False),
        ],
        responses={
            200: CommandeListSerializer(many=True),
            403: OpenApiResponse(description="Accès réservé : Serveur, Chef Cuisinier, Admin, Manager"),
        },
        tags=["Commandes"],
    )
    def get(self, request):
        if not self._check_access(request.user):
            return err(
                message="Accès réservé : Serveur, Chef Cuisinier, Admin, Manager.",
                code=status.HTTP_403_FORBIDDEN,
            )

        qs = Commande.objects.filter(
            restaurant=request.user.restaurant
        ).select_related('table', 'serveur_ayant_servi', 'cuisinier_ayant_prepare')\
         .order_by('-date_commande')

        statut   = request.query_params.get('statut')
        table_id = request.query_params.get('table_id')

        if statut and statut in ('en_attente', 'prete', 'servie', 'payee'):
            qs = qs.filter(statut=statut)
        if table_id:
            qs = qs.filter(table_id=table_id)

        return ok(data={
            'count': qs.count(),
            'commandes': CommandeListSerializer(qs, many=True).data,
        })


# ─────────────────────────────────────────────────────────────────────────────
# DÉTAIL D'UNE COMMANDE
# ─────────────────────────────────────────────────────────────────────────────

class CommandeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Détail d'une commande",
        description="Retourne le détail complet d'une commande. Table : sa session courante uniquement. Staff : toute commande du restaurant.",
        responses={
            200: CommandeDetailSerializer,
            403: OpenApiResponse(description="Accès refusé"),
            404: OpenApiResponse(description="Commande non trouvée"),
        },
        tags=["Commandes"],
    )
    def get(self, request, pk):
        user = request.user

        commande = get_object_or_404(
            Commande.objects.prefetch_related('items__plat'),
            pk=pk,
            restaurant=user.restaurant,
        )

        if user.is_table():
            if commande.table != user:
                return err(message="Accès refusé.", code=status.HTTP_403_FORBIDDEN)
            session = _session_active(request)
            if session and commande.session and commande.session != session:
                return err(
                    message="Cette commande n'appartient pas à votre session courante.",
                    code=status.HTTP_403_FORBIDDEN,
                )
        elif not any(getattr(user, r)() for r in ('is_serveur', 'is_chef_cuisinier', 'is_admin', 'is_manager')):
            return err(message="Accès non autorisé.", code=status.HTTP_403_FORBIDDEN)

        return ok(data=CommandeDetailSerializer(commande, context={'request': request}).data)


# ─────────────────────────────────────────────────────────────────────────────
# VUE CUISINE — Cuisinier / Chef Cuisinier
# ─────────────────────────────────────────────────────────────────────────────

class CuisinierCommandesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="File des commandes cuisine",
        description="Retourne les commandes ayant des plats nécessitant validation cuisine. Filtre : ?statut=en_attente|prete. Accès : Cuisinier, Chef Cuisinier.",
        parameters=[
            OpenApiParameter('statut', OpenApiTypes.STR, description="en_attente (défaut) | prete", required=False),
        ],
        responses={
            200: CommandeCuisinierSerializer(many=True),
            403: OpenApiResponse(description="Accès réservé aux Cuisiniers"),
        },
        tags=["Cuisine"],
    )
    def get(self, request):
        if not request.user.is_cuisinier_any():
            return err(message="Accès réservé aux Cuisiniers.", code=status.HTTP_403_FORBIDDEN)

        statut = request.query_params.get('statut', 'en_attente')
        if statut not in ('en_attente', 'prete'):
            statut = 'en_attente'

        qs = Commande.objects.filter(
            restaurant=request.user.restaurant,
            statut=statut,
            items__plat__necessite_validation_cuisine=True,
        ).distinct().prefetch_related('items__plat').order_by('date_commande')

        return ok(data={
            'count': qs.count(),
            'commandes': CommandeCuisinierSerializer(qs, many=True).data,
        })


class CommandePreteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Marquer une commande comme PRÊTE",
        description="Le cuisinier marque la commande comme prête à être servie. Statut requis : EN_ATTENTE. Accès : Cuisinier, Chef Cuisinier.",
        responses={
            200: CommandeDetailSerializer,
            400: OpenApiResponse(description="Statut invalide"),
            403: OpenApiResponse(description="Accès réservé aux Cuisiniers"),
            404: OpenApiResponse(description="Commande non trouvée"),
        },
        tags=["Cuisine"],
    )
    def post(self, request, pk):
        if not request.user.is_cuisinier_any():
            return err(message="Accès réservé aux Cuisiniers.", code=status.HTTP_403_FORBIDDEN)

        commande = get_object_or_404(Commande, pk=pk, restaurant=request.user.restaurant)
        s = CommandePreteSerializer(data={}, context={'commande': commande})
        if s.is_valid():
            commande = s.save(cuisinier=request.user)
            return ok(
                data=CommandeDetailSerializer(commande, context={'request': request}).data,
                message=f"Commande #{commande.id} marquée PRÊTE.",
            )
        return err(errors=s.errors, message="Action impossible.")


# ─────────────────────────────────────────────────────────────────────────────
# VUE SERVEUR — SERVIE & PAYÉE
# ─────────────────────────────────────────────────────────────────────────────

class CommandeServieView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Marquer une commande comme SERVIE",
        description="Le serveur marque la commande comme servie. Statut requis : PRÊTE (ou sans étape cuisine). CDC §7.1 étape 4. Accès : Serveur uniquement.",
        responses={
            200: CommandeDetailSerializer,
            400: OpenApiResponse(description="Statut invalide"),
            403: OpenApiResponse(description="Accès réservé aux Serveurs"),
            404: OpenApiResponse(description="Commande non trouvée"),
        },
        tags=["Service"],
    )
    def post(self, request, pk):
        if not request.user.is_serveur():
            return err(message="Accès réservé aux Serveurs.", code=status.HTTP_403_FORBIDDEN)

        commande = get_object_or_404(Commande, pk=pk, restaurant=request.user.restaurant)
        s = CommandeServieSerializer(data={}, context={'commande': commande})
        if s.is_valid():
            commande = s.save(serveur=request.user)
            return ok(
                data=CommandeDetailSerializer(commande, context={'request': request}).data,
                message=f"Commande #{commande.id} marquée SERVIE.",
            )
        return err(errors=s.errors, message="Action impossible.")


class CommandePayeeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Marquer une commande comme PAYÉE",
        description="Le serveur valide le paiement. Statut requis : SERVIE. Déclenche l'expiration de la session QR (1 min). CDC §7.1 étape 5. Accès : Serveur uniquement.",
        responses={
            200: CommandeDetailSerializer,
            400: OpenApiResponse(description="Statut invalide"),
            403: OpenApiResponse(description="Accès réservé aux Serveurs"),
            404: OpenApiResponse(description="Commande non trouvée"),
        },
        tags=["Service"],
    )
    def post(self, request, pk):
        if not request.user.is_serveur():
            return err(message="Accès réservé aux Serveurs.", code=status.HTTP_403_FORBIDDEN)

        commande = get_object_or_404(Commande, pk=pk, restaurant=request.user.restaurant)
        s = CommandePayeeSerializer(data={}, context={'commande': commande})
        if s.is_valid():
            commande = s.save(serveur=request.user)
            return ok(
                data=CommandeDetailSerializer(commande, context={'request': request}).data,
                message=(
                    f"Commande #{commande.id} marquée PAYÉE. "
                    "En attente de remise au comptable."
                ),
            )
        return err(errors=s.errors, message="Action impossible.")


# ─────────────────────────────────────────────────────────────────────────────
# REÇU PDF
# ─────────────────────────────────────────────────────────────────────────────

class CommandeRecuView(APIView):
    permission_classes = [IsAuthenticated]

    ROLES_STAFF = ('is_serveur', 'is_comptable', 'is_chef_cuisinier', 'is_admin', 'is_manager')

    @extend_schema(
        summary="Télécharger le reçu PDF",
        description="Génère et retourne le reçu PDF d'une commande. Table : sa commande de sa session courante. Staff : toute commande du restaurant.",
        responses={
            200: OpenApiResponse(description="Fichier PDF"),
            403: OpenApiResponse(description="Accès non autorisé"),
            404: OpenApiResponse(description="Commande non trouvée"),
            500: OpenApiResponse(description="Erreur génération PDF"),
        },
        tags=["Commandes"],
    )
    def get(self, request, pk):
        user = request.user

        commande = get_object_or_404(
            Commande.objects.select_related(
                'table', 'restaurant', 'serveur_ayant_servi', 'cuisinier_ayant_prepare'
            ).prefetch_related('items__plat'),
            pk=pk,
            restaurant=user.restaurant,
        )

        if user.is_table():
            if commande.table != user:
                return err(message="Ce reçu ne vous appartient pas.", code=status.HTTP_403_FORBIDDEN)
        elif not any(getattr(user, r)() for r in self.ROLES_STAFF):
            return err(message="Accès non autorisé.", code=status.HTTP_403_FORBIDDEN)

        try:
            pdf_buffer = generer_recu_pdf(commande)
            filename   = (
                f"recu_commande_{commande.id}_"
                f"{commande.date_commande.strftime('%Y%m%d_%H%M')}.pdf"
            )
            response = HttpResponse(pdf_buffer, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        except Exception as e:
            return err(
                message=f"Erreur génération PDF : {str(e)}",
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ─────────────────────────────────────────────────────────────────────────────
# SUPPRESSION — Admin uniquement
# ─────────────────────────────────────────────────────────────────────────────

class CommandeDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Supprimer une commande (Admin uniquement)",
        description="Supprime définitivement une commande. Action irréversible. CDC §5.6 / §10.5. Accès : Admin uniquement.",
        responses={
            200: OpenApiResponse(description="Commande supprimée"),
            403: OpenApiResponse(description="Seul l'Admin peut supprimer une commande"),
            404: OpenApiResponse(description="Commande non trouvée"),
        },
        tags=["Commandes"],
    )
    def delete(self, request, pk):
        if not request.user.is_admin():
            return err(
                message="Seul l'Admin peut supprimer une commande.",
                code=status.HTTP_403_FORBIDDEN,
            )
        commande = get_object_or_404(Commande, pk=pk, restaurant=request.user.restaurant)
        commande_id = commande.id
        commande.delete()
        return ok(message=f"Commande #{commande_id} supprimée.")