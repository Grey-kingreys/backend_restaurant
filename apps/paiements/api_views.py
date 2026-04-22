# apps/paiements/api_views.py
import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import (
    CaisseGenerale, CaisseGlobale, CaisseComptable,
    RemiseServeur, Paiement, Depense,
)
from .serializers import (
    CaisseGeneraleSerializer,
    CaisseGeneraleInitSerializer,
    CaisseGlobaleSerializer,
    CaisseGlobaleFermerSerializer,
    CaisseComptableSerializer,
    CaisseComptableListSerializer,
    CaisseComptableOuvrirSerializer,
    ApprovisionnerSerializer,
    DepenseCreateSerializer,
    DepenseSerializer,
    CaisseComptableFermerSerializer,
    RemiseServeurSerializer,
    RemiseValiderSerializer,
    PaiementSerializer,
    DashboardComptableSerializer,
)
from apps.accounts.permissions import IsRestaurantActive

logger = logging.getLogger(__name__)


def ok(data=None, message="", code=status.HTTP_200_OK):
    return Response(
        {"success": True, "data": data, "message": message},
        status=code,
    )


def err(errors=None, message="", code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {"success": False, "errors": errors, "message": message},
        status=code,
    )


# ─────────────────────────────────────────────────────────────────────────────
# CAISSE GENERALE — Admin & Manager uniquement
# ─────────────────────────────────────────────────────────────────────────────

class CaisseGeneraleView(APIView):
    """
    GET  /api/paiements/caisse-generale/       — Solde et infos
    POST /api/paiements/caisse-generale/init/  — Initialiser le solde (Admin)
    """
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    def _check_admin_manager(self, user):
        return user.is_admin_or_manager()

    @extend_schema(
        summary="Caisse Generale du restaurant",
        description=(
            "Retourne le solde et les informations de la Caisse Generale. "
            "Acces : Admin, Manager."
        ),
        responses={
            200: CaisseGeneraleSerializer,
            403: OpenApiResponse(description="Acces reserve Admin/Manager"),
            404: OpenApiResponse(description="Caisse non initialisee"),
        },
        tags=["Paiements - Caisse Generale"],
    )
    def get(self, request):
        if not self._check_admin_manager(request.user):
            return err(
                message="Acces reserve a l'Administrateur ou au Manager.",
                code=status.HTTP_403_FORBIDDEN,
            )
        try:
            caisse = CaisseGenerale.objects.get(restaurant=request.user.restaurant)
        except CaisseGenerale.DoesNotExist:
            return err(
                message="La Caisse Generale n'a pas encore ete initialisee.",
                code=status.HTTP_404_NOT_FOUND,
            )
        return ok(data=CaisseGeneraleSerializer(caisse).data)


class CaisseGeneraleInitView(APIView):
    """POST /api/paiements/caisse-generale/init/ — Admin uniquement."""
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    @extend_schema(
        summary="Initialiser le solde de la Caisse Generale",
        description=(
            "Cree ou reinitialise le solde initial de la Caisse Generale. "
            "A utiliser une seule fois lors de la configuration du restaurant. "
            "Acces : Admin uniquement."
        ),
        request=CaisseGeneraleInitSerializer,
        responses={
            200: CaisseGeneraleSerializer,
            400: OpenApiResponse(description="Donnees invalides"),
            403: OpenApiResponse(description="Acces reserve a l'Admin"),
        },
        tags=["Paiements - Caisse Generale"],
    )
    def post(self, request):
        if not request.user.is_admin():
            return err(
                message="Seul l'Administrateur peut initialiser la Caisse Generale.",
                code=status.HTTP_403_FORBIDDEN,
            )
        caisse, _ = CaisseGenerale.objects.get_or_create(
            restaurant=request.user.restaurant,
        )
        s = CaisseGeneraleInitSerializer(data=request.data)
        if s.is_valid():
            caisse = s.save(caisse)
            return ok(
                data=CaisseGeneraleSerializer(caisse).data,
                message="Caisse Generale initialisee.",
            )
        return err(errors=s.errors, message="Donnees invalides.")


# ─────────────────────────────────────────────────────────────────────────────
# CAISSE GLOBALE
# ─────────────────────────────────────────────────────────────────────────────

class CaisseGlobaleListView(APIView):
    """
    GET /api/paiements/caisse-globale/
    Liste des caisses globales du restaurant (historique).
    Acces : Comptable, Admin, Manager.
    """
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    ROLES_AUTORISES = ('is_comptable', 'is_admin', 'is_manager')

    def _check_access(self, user):
        return any(getattr(user, r)() for r in self.ROLES_AUTORISES)

    @extend_schema(
        summary="Liste des Caisses Globales (historique)",
        description=(
            "Retourne la liste paginee des caisses globales du restaurant. "
            "Filtre : ?is_closed=true/false. "
            "Acces : Comptable, Admin, Manager."
        ),
        parameters=[
            OpenApiParameter(
                'is_closed', OpenApiTypes.BOOL,
                description="true = fermees, false = ouverte active",
                required=False,
            ),
        ],
        responses={
            200: CaisseGlobaleSerializer(many=True),
            403: OpenApiResponse(description="Acces reserve"),
        },
        tags=["Paiements - Caisse Globale"],
    )
    def get(self, request):
        if not self._check_access(request.user):
            return err(
                message="Acces reserve au Comptable, Admin ou Manager.",
                code=status.HTTP_403_FORBIDDEN,
            )
        qs = CaisseGlobale.objects.filter(
            restaurant=request.user.restaurant
        ).order_by('-date_ouverture')

        is_closed = request.query_params.get('is_closed')
        if is_closed is not None:
            qs = qs.filter(is_closed=is_closed.lower() == 'true')

        return ok(data={
            'count': qs.count(),
            'caisses': CaisseGlobaleSerializer(qs, many=True).data,
        })


class CaisseGlobaleActiveView(APIView):
    """
    GET  /api/paiements/caisse-globale/active/  — Caisse du jour
    POST /api/paiements/caisse-globale/active/fermer/ — Fermeture
    Acces : Comptable, Admin, Manager.
    """
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    ROLES_AUTORISES = ('is_comptable', 'is_admin', 'is_manager')

    def _check_access(self, user):
        return any(getattr(user, r)() for r in self.ROLES_AUTORISES)

    def _get_active(self, request):
        return CaisseGlobale.objects.filter(
            restaurant=request.user.restaurant,
            is_closed=False,
        ).first()

    @extend_schema(
        summary="Caisse Globale active (journee en cours)",
        responses={
            200: CaisseGlobaleSerializer,
            403: OpenApiResponse(description="Acces reserve"),
            404: OpenApiResponse(description="Aucune caisse ouverte"),
        },
        tags=["Paiements - Caisse Globale"],
    )
    def get(self, request):
        if not self._check_access(request.user):
            return err(
                message="Acces reserve au Comptable, Admin ou Manager.",
                code=status.HTTP_403_FORBIDDEN,
            )
        caisse = self._get_active(request)
        if not caisse:
            return err(
                message="Aucune Caisse Globale ouverte pour aujourd'hui.",
                code=status.HTTP_404_NOT_FOUND,
            )
        return ok(data=CaisseGlobaleSerializer(caisse).data)


class CaisseGlobaleFermerView(APIView):
    """POST /api/paiements/caisse-globale/active/fermer/"""
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    ROLES_AUTORISES = ('is_comptable', 'is_admin', 'is_manager')

    def _check_access(self, user):
        return any(getattr(user, r)() for r in self.ROLES_AUTORISES)

    @extend_schema(
        summary="Fermer la Caisse Globale du jour",
        description=(
            "Ferme la caisse globale active. Le solde est transfere "
            "dans la Caisse Generale. Operation irreversible. "
            "Acces : Comptable, Admin, Manager."
        ),
        request=CaisseGlobaleFermerSerializer,
        responses={
            200: CaisseGlobaleSerializer,
            400: OpenApiResponse(description="Donnees invalides ou caisse deja fermee"),
            403: OpenApiResponse(description="Acces reserve"),
            404: OpenApiResponse(description="Aucune caisse ouverte"),
        },
        tags=["Paiements - Caisse Globale"],
    )
    def post(self, request):
        if not self._check_access(request.user):
            return err(
                message="Acces reserve au Comptable, Admin ou Manager.",
                code=status.HTTP_403_FORBIDDEN,
            )
        caisse = CaisseGlobale.objects.filter(
            restaurant=request.user.restaurant,
            is_closed=False,
        ).first()
        if not caisse:
            return err(
                message="Aucune Caisse Globale ouverte a fermer.",
                code=status.HTTP_404_NOT_FOUND,
            )

        # Verifier qu'il n'y a plus de remises en attente
        remises_en_attente = RemiseServeur.objects.filter(
            caisse_globale=caisse,
            valide=False,
        ).count()
        if remises_en_attente > 0:
            return err(
                message=(
                    f"Impossible de fermer la caisse : "
                    f"{remises_en_attente} remise(s) serveur en attente de validation."
                ),
            )

        s = CaisseGlobaleFermerSerializer(
            data=request.data,
            context={'caisse': caisse},
        )
        if s.is_valid():
            caisse = s.save(fermee_par=request.user)
            return ok(
                data=CaisseGlobaleSerializer(caisse).data,
                message=f"Caisse Globale du {caisse.date_ouverture} fermee. "
                        f"Solde de {caisse.solde:,.0f} GNF transfère dans la Caisse Generale.".replace(',', ' '),
            )
        return err(errors=s.errors, message="Donnees invalides.")


class CaisseGlobaleOuvrirView(APIView):
    """
    POST /api/paiements/caisse-globale/ouvrir/
    Ouvre manuellement une Caisse Globale pour aujourd'hui.
    Normalement fait par Celery a 5h00, mais disponible manuellement.
    Acces : Admin uniquement.
    """
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    @extend_schema(
        summary="Ouvrir manuellement la Caisse Globale du jour",
        description=(
            "Ouvre une nouvelle Caisse Globale pour la date du jour. "
            "En production, cette action est effectuee automatiquement "
            "par Celery a 5h00. Acces : Admin uniquement."
        ),
        request=None,
        responses={
            201: CaisseGlobaleSerializer,
            400: OpenApiResponse(description="Une caisse est deja ouverte"),
            403: OpenApiResponse(description="Acces reserve a l'Admin"),
        },
        tags=["Paiements - Caisse Globale"],
    )
    def post(self, request):
        if not request.user.is_admin():
            return err(
                message="Seul l'Administrateur peut ouvrir manuellement la Caisse Globale.",
                code=status.HTTP_403_FORBIDDEN,
            )
        restaurant = request.user.restaurant
        deja_ouverte = CaisseGlobale.objects.filter(
            restaurant=restaurant, is_closed=False
        ).exists()
        if deja_ouverte:
            return err(
                message="Une Caisse Globale est deja ouverte pour aujourd'hui."
            )

        today = timezone.localdate()
        # Verifier qu'il n'y a pas deja une caisse pour aujourd'hui
        if CaisseGlobale.objects.filter(restaurant=restaurant, date_ouverture=today).exists():
            return err(
                message=f"Une caisse a deja ete ouverte pour le {today}."
            )

        caisse = CaisseGlobale.objects.create(
            restaurant=restaurant,
            date_ouverture=today,
        )
        return ok(
            data=CaisseGlobaleSerializer(caisse).data,
            message=f"Caisse Globale du {today} ouverte.",
            code=status.HTTP_201_CREATED,
        )


# ─────────────────────────────────────────────────────────────────────────────
# CAISSE COMPTABLE
# ─────────────────────────────────────────────────────────────────────────────

class CaisseComptableListView(APIView):
    """
    GET  /api/paiements/caisse-comptable/        — Mes caisses (comptable) ou toutes (admin/manager)
    POST /api/paiements/caisse-comptable/ouvrir/ — Ouvrir une caisse (comptable)
    """
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    ROLES_AUTORISES = ('is_comptable', 'is_admin', 'is_manager')

    def _check_access(self, user):
        return any(getattr(user, r)() for r in self.ROLES_AUTORISES)

    @extend_schema(
        summary="Mes caisses comptables",
        description=(
            "Comptable : retourne uniquement ses propres caisses. "
            "Admin / Manager : retourne toutes les caisses du restaurant. "
            "Filtre : ?is_closed=true/false."
        ),
        parameters=[
            OpenApiParameter(
                'is_closed', OpenApiTypes.BOOL,
                description="Filtrer par statut ouvert/ferme",
                required=False,
            ),
        ],
        responses={
            200: CaisseComptableListSerializer(many=True),
            403: OpenApiResponse(description="Acces reserve"),
        },
        tags=["Paiements - Caisse Comptable"],
    )
    def get(self, request):
        if not self._check_access(request.user):
            return err(
                message="Acces reserve au Comptable, Admin ou Manager.",
                code=status.HTTP_403_FORBIDDEN,
            )
        qs = CaisseComptable.objects.filter(
            restaurant=request.user.restaurant
        )
        # Le comptable ne voit que ses propres caisses
        if request.user.is_comptable():
            qs = qs.filter(comptable=request.user)

        is_closed = request.query_params.get('is_closed')
        if is_closed is not None:
            qs = qs.filter(is_closed=is_closed.lower() == 'true')

        qs = qs.order_by('-opened_at')
        return ok(data={
            'count': qs.count(),
            'caisses': CaisseComptableListSerializer(qs, many=True).data,
        })


class CaisseComptableOuvrirView(APIView):
    """POST /api/paiements/caisse-comptable/ouvrir/"""
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    @extend_schema(
        summary="Ouvrir une Caisse Comptable",
        description=(
            "Le comptable ouvre sa caisse en debut de journee. "
            "Un comptable ne peut avoir qu'une seule caisse ouverte a la fois. "
            "Acces : Comptable uniquement."
        ),
        request=None,
        responses={
            201: CaisseComptableSerializer,
            400: OpenApiResponse(description="Une caisse est deja ouverte"),
            403: OpenApiResponse(description="Acces reserve au Comptable"),
        },
        tags=["Paiements - Caisse Comptable"],
    )
    def post(self, request):
        if not request.user.is_comptable():
            return err(
                message="Seul le Comptable peut ouvrir une Caisse Comptable.",
                code=status.HTTP_403_FORBIDDEN,
            )
        s = CaisseComptableOuvrirSerializer(
            data={}, context={'request': request}
        )
        if s.is_valid():
            caisse = s.save()
            return ok(
                data=CaisseComptableSerializer(caisse).data,
                message="Caisse Comptable ouverte.",
                code=status.HTTP_201_CREATED,
            )
        return err(errors=s.errors, message="Impossible d'ouvrir la caisse.")


class CaisseComptableDetailView(APIView):
    """GET /api/paiements/caisse-comptable/<pk>/"""
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    def _get_caisse(self, pk, request):
        qs = CaisseComptable.objects.filter(
            restaurant=request.user.restaurant
        )
        if request.user.is_comptable():
            qs = qs.filter(comptable=request.user)
        return get_object_or_404(qs, pk=pk)

    @extend_schema(
        summary="Detail d'une Caisse Comptable",
        description="Inclut tous les mouvements. Comptable : sa caisse uniquement.",
        responses={
            200: CaisseComptableSerializer,
            403: OpenApiResponse(description="Acces refuse"),
            404: OpenApiResponse(description="Caisse introuvable"),
        },
        tags=["Paiements - Caisse Comptable"],
    )
    def get(self, request, pk):
        if not any(
            getattr(request.user, r)()
            for r in ('is_comptable', 'is_admin', 'is_manager')
        ):
            return err(
                message="Acces reserve au Comptable, Admin ou Manager.",
                code=status.HTTP_403_FORBIDDEN,
            )
        caisse = self._get_caisse(pk, request)
        return ok(data=CaisseComptableSerializer(caisse).data)


class CaisseComptableActiveView(APIView):
    """GET /api/paiements/caisse-comptable/active/ — Ma caisse ouverte"""
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    @extend_schema(
        summary="Ma Caisse Comptable active",
        description=(
            "Retourne la caisse comptable ouverte du comptable connecte. "
            "Acces : Comptable uniquement."
        ),
        responses={
            200: CaisseComptableSerializer,
            403: OpenApiResponse(description="Acces reserve au Comptable"),
            404: OpenApiResponse(description="Aucune caisse ouverte"),
        },
        tags=["Paiements - Caisse Comptable"],
    )
    def get(self, request):
        if not request.user.is_comptable():
            return err(
                message="Acces reserve au Comptable.",
                code=status.HTTP_403_FORBIDDEN,
            )
        caisse = CaisseComptable.objects.filter(
            comptable=request.user,
            is_closed=False,
        ).prefetch_related('mouvements').first()
        if not caisse:
            return err(
                message="Aucune Caisse Comptable ouverte.",
                code=status.HTTP_404_NOT_FOUND,
            )
        return ok(data=CaisseComptableSerializer(caisse).data)


class CaisseComptableApprovisionnerView(APIView):
    """POST /api/paiements/caisse-comptable/<pk>/approvisionner/"""
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    @extend_schema(
        summary="Approvisionner la Caisse Comptable",
        description=(
            "Transfere un montant de la Caisse Generale vers la Caisse Comptable. "
            "Verifie que la Caisse Generale a un solde suffisant. "
            "Acces : Comptable (sa propre caisse), Admin, Manager."
        ),
        request=ApprovisionnerSerializer,
        responses={
            200: CaisseComptableSerializer,
            400: OpenApiResponse(description="Solde insuffisant ou caisse fermee"),
            403: OpenApiResponse(description="Acces refuse"),
            404: OpenApiResponse(description="Caisse introuvable"),
        },
        tags=["Paiements - Caisse Comptable"],
    )
    def post(self, request, pk):
        if not any(
            getattr(request.user, r)()
            for r in ('is_comptable', 'is_admin', 'is_manager')
        ):
            return err(
                message="Acces reserve au Comptable, Admin ou Manager.",
                code=status.HTTP_403_FORBIDDEN,
            )
        qs = CaisseComptable.objects.filter(restaurant=request.user.restaurant)
        if request.user.is_comptable():
            qs = qs.filter(comptable=request.user)
        caisse = get_object_or_404(qs, pk=pk)

        s = ApprovisionnerSerializer(
            data=request.data,
            context={'caisse': caisse},
        )
        if s.is_valid():
            caisse = s.save(effectue_par=request.user)
            return ok(
                data=CaisseComptableSerializer(caisse).data,
                message=f"Caisse approvisionnee de {s.validated_data['montant']:,.0f} GNF.".replace(',', ' '),
            )
        return err(errors=s.errors, message="Donnees invalides.")


class DepenseCreateView(APIView):
    """POST /api/paiements/caisse-comptable/<pk>/depense/"""
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    @extend_schema(
        summary="Enregistrer une depense",
        description=(
            "Enregistre une depense sur la Caisse Comptable. "
            "Impossible si le solde est insuffisant. "
            "Acces : Comptable (sa propre caisse uniquement)."
        ),
        request=DepenseCreateSerializer,
        responses={
            201: DepenseSerializer,
            400: OpenApiResponse(description="Solde insuffisant ou donnees invalides"),
            403: OpenApiResponse(description="Acces reserve au Comptable"),
            404: OpenApiResponse(description="Caisse introuvable"),
        },
        tags=["Paiements - Caisse Comptable"],
    )
    def post(self, request, pk):
        if not request.user.is_comptable():
            return err(
                message="Seul le Comptable peut enregistrer des depenses.",
                code=status.HTTP_403_FORBIDDEN,
            )
        caisse = get_object_or_404(
            CaisseComptable,
            pk=pk,
            comptable=request.user,
            restaurant=request.user.restaurant,
        )
        s = DepenseCreateSerializer(
            data=request.data,
            context={'caisse': caisse},
        )
        if s.is_valid():
            depense = s.save(enregistree_par=request.user)
            return ok(
                data=DepenseSerializer(depense).data,
                message="Depense enregistree.",
                code=status.HTTP_201_CREATED,
            )
        return err(errors=s.errors, message="Donnees invalides.")


class DepenseListView(APIView):
    """GET /api/paiements/caisse-comptable/<pk>/depenses/"""
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    @extend_schema(
        summary="Liste des depenses d'une Caisse Comptable",
        responses={
            200: DepenseSerializer(many=True),
            403: OpenApiResponse(description="Acces refuse"),
            404: OpenApiResponse(description="Caisse introuvable"),
        },
        tags=["Paiements - Caisse Comptable"],
    )
    def get(self, request, pk):
        if not any(
            getattr(request.user, r)()
            for r in ('is_comptable', 'is_admin', 'is_manager')
        ):
            return err(
                message="Acces reserve.",
                code=status.HTTP_403_FORBIDDEN,
            )
        qs = CaisseComptable.objects.filter(restaurant=request.user.restaurant)
        if request.user.is_comptable():
            qs = qs.filter(comptable=request.user)
        caisse = get_object_or_404(qs, pk=pk)

        depenses = Depense.objects.filter(
            caisse_comptable=caisse
        ).order_by('-date_depense')
        return ok(data={
            'count': depenses.count(),
            'depenses': DepenseSerializer(depenses, many=True).data,
        })


class CaisseComptableFermerView(APIView):
    """POST /api/paiements/caisse-comptable/<pk>/fermer/"""
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    @extend_schema(
        summary="Fermer la Caisse Comptable",
        description=(
            "Ferme la caisse avec reconciliation physique. "
            "Le solde restant est transfere dans la Caisse Generale. "
            "Operation irreversible. "
            "Acces : Comptable (sa propre caisse uniquement)."
        ),
        request=CaisseComptableFermerSerializer,
        responses={
            200: CaisseComptableSerializer,
            400: OpenApiResponse(description="Donnees invalides ou caisse deja fermee"),
            403: OpenApiResponse(description="Acces reserve au Comptable"),
            404: OpenApiResponse(description="Caisse introuvable"),
        },
        tags=["Paiements - Caisse Comptable"],
    )
    def post(self, request, pk):
        if not request.user.is_comptable():
            return err(
                message="Seul le Comptable peut fermer sa caisse.",
                code=status.HTTP_403_FORBIDDEN,
            )
        caisse = get_object_or_404(
            CaisseComptable,
            pk=pk,
            comptable=request.user,
            restaurant=request.user.restaurant,
        )
        s = CaisseComptableFermerSerializer(
            data=request.data,
            context={'caisse': caisse},
        )
        if s.is_valid():
            caisse = s.save()
            return ok(
                data=CaisseComptableSerializer(caisse).data,
                message=(
                    "Caisse Comptable fermee. "
                    f"Solde de {caisse.solde:,.0f} GNF transfere dans la Caisse Generale.".replace(',', ' ')
                ),
            )
        return err(errors=s.errors, message="Donnees invalides.")


# ─────────────────────────────────────────────────────────────────────────────
# REMISES SERVEUR
# ─────────────────────────────────────────────────────────────────────────────

class RemiseServeurListView(APIView):
    """
    GET /api/paiements/remises/
    Liste des remises selon le role :
    - Serveur : ses propres remises
    - Comptable : remises en attente de validation
    - Admin / Manager : toutes les remises
    """
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    ROLES_AUTORISES = ('is_serveur', 'is_comptable', 'is_admin', 'is_manager')

    def _check_access(self, user):
        return any(getattr(user, r)() for r in self.ROLES_AUTORISES)

    @extend_schema(
        summary="Liste des remises serveurs",
        description=(
            "Serveur : ses remises uniquement. "
            "Comptable : remises en attente de validation. "
            "Admin/Manager : toutes les remises. "
            "Filtre : ?valide=true/false."
        ),
        parameters=[
            OpenApiParameter(
                'valide', OpenApiTypes.BOOL,
                description="Filtrer par statut valide",
                required=False,
            ),
        ],
        responses={
            200: RemiseServeurSerializer(many=True),
            403: OpenApiResponse(description="Acces refuse"),
        },
        tags=["Paiements - Remises"],
    )
    def get(self, request):
        if not self._check_access(request.user):
            return err(
                message="Acces reserve.",
                code=status.HTTP_403_FORBIDDEN,
            )

        # Filtrage par restaurant d'abord (isolation SaaS)
        qs = RemiseServeur.objects.filter(
            caisse_globale__restaurant=request.user.restaurant
        ).select_related(
            'serveur', 'validee_par', 'paiement__commande__table'
        ).order_by('-created_at')

        # Filtrage par role
        if request.user.is_serveur():
            qs = qs.filter(serveur=request.user)
        elif request.user.is_comptable():
            # Par defaut le comptable voit les non validees
            valide_param = request.query_params.get('valide')
            if valide_param is None:
                qs = qs.filter(valide=False)

        # Filtre query param optionnel
        valide = request.query_params.get('valide')
        if valide is not None and not (request.user.is_comptable() and request.query_params.get('valide') is None):
            qs = qs.filter(valide=valide.lower() == 'true')

        return ok(data={
            'count': qs.count(),
            'remises': RemiseServeurSerializer(qs, many=True).data,
        })


class RemiseServeurDetailView(APIView):
    """GET /api/paiements/remises/<pk>/"""
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    ROLES_AUTORISES = ('is_serveur', 'is_comptable', 'is_admin', 'is_manager')

    @extend_schema(
        summary="Detail d'une remise serveur",
        responses={
            200: RemiseServeurSerializer,
            403: OpenApiResponse(description="Acces refuse"),
            404: OpenApiResponse(description="Remise introuvable"),
        },
        tags=["Paiements - Remises"],
    )
    def get(self, request, pk):
        if not any(getattr(request.user, r)() for r in self.ROLES_AUTORISES):
            return err(
                message="Acces refuse.",
                code=status.HTTP_403_FORBIDDEN,
            )
        qs = RemiseServeur.objects.filter(
            caisse_globale__restaurant=request.user.restaurant
        )
        if request.user.is_serveur():
            qs = qs.filter(serveur=request.user)

        remise = get_object_or_404(qs, pk=pk)
        return ok(data=RemiseServeurSerializer(remise).data)


class RemiseValiderView(APIView):
    """
    POST /api/paiements/remises/<pk>/valider/
    Le comptable valide physiquement la remise du serveur.
    La Caisse Globale est creditee du montant physique recu.
    """
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    @extend_schema(
        summary="Valider une remise serveur",
        description=(
            "Le comptable saisit le montant physique recu et valide. "
            "Si ecart avec montant virtuel -> motif obligatoire. "
            "La Caisse Globale est creditee du montant physique. "
            "Acces : Comptable uniquement."
        ),
        request=RemiseValiderSerializer,
        responses={
            200: RemiseServeurSerializer,
            400: OpenApiResponse(description="Donnees invalides ou remise deja validee"),
            403: OpenApiResponse(description="Acces reserve au Comptable"),
            404: OpenApiResponse(description="Remise introuvable"),
        },
        tags=["Paiements - Remises"],
    )
    def post(self, request, pk):
        if not request.user.is_comptable():
            return err(
                message="Seul le Comptable peut valider les remises.",
                code=status.HTTP_403_FORBIDDEN,
            )

        remise = get_object_or_404(
            RemiseServeur,
            pk=pk,
            caisse_globale__restaurant=request.user.restaurant,
        )

        # Verifier qu'une caisse globale est active
        caisse_globale = remise.caisse_globale
        if caisse_globale.is_closed:
            return err(
                message="La Caisse Globale associee est deja fermee."
            )

        s = RemiseValiderSerializer(
            data=request.data,
            context={'remise': remise},
        )
        if s.is_valid():
            remise = s.save(validee_par=request.user)
            return ok(
                data=RemiseServeurSerializer(remise).data,
                message=(
                    f"Remise validee. "
                    f"Caisse Globale creditee de "
                    f"{remise.montant_physique:,.0f} GNF.".replace(',', ' ')
                ),
            )
        return err(errors=s.errors, message="Donnees invalides.")


# ─────────────────────────────────────────────────────────────────────────────
# PAIEMENTS — Lecture
# ─────────────────────────────────────────────────────────────────────────────

class PaiementListView(APIView):
    """
    GET /api/paiements/
    Liste des paiements du restaurant.
    Acces : Comptable, Admin, Manager.
    """
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    ROLES_AUTORISES = ('is_comptable', 'is_admin', 'is_manager')

    @extend_schema(
        summary="Liste des paiements",
        description=(
            "Retourne la liste des paiements du restaurant. "
            "Acces : Comptable, Admin, Manager."
        ),
        responses={
            200: PaiementSerializer(many=True),
            403: OpenApiResponse(description="Acces reserve"),
        },
        tags=["Paiements"],
    )
    def get(self, request):
        if not any(getattr(request.user, r)() for r in self.ROLES_AUTORISES):
            return err(
                message="Acces reserve au Comptable, Admin ou Manager.",
                code=status.HTTP_403_FORBIDDEN,
            )
        qs = Paiement.objects.filter(
            commande__restaurant=request.user.restaurant
        ).select_related('commande__table').order_by('-date_paiement')

        return ok(data={
            'count': qs.count(),
            'paiements': PaiementSerializer(qs, many=True).data,
        })


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD COMPTABLE
# ─────────────────────────────────────────────────────────────────────────────

class DashboardComptableView(APIView):
    """
    GET /api/paiements/dashboard/
    Stats du dashboard pour le comptable.
    Acces : Comptable uniquement.
    """
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    @extend_schema(
        summary="Dashboard Comptable",
        description=(
            "Retourne un apercu rapide : caisse globale active, "
            "ma caisse ouverte, remises en attente, "
            "remises et depenses du jour. "
            "Acces : Comptable uniquement."
        ),
        responses={
            200: DashboardComptableSerializer,
            403: OpenApiResponse(description="Acces reserve au Comptable"),
        },
        tags=["Paiements - Dashboard"],
    )
    def get(self, request):
        if not request.user.is_comptable():
            return err(
                message="Acces reserve au Comptable.",
                code=status.HTTP_403_FORBIDDEN,
            )
        from decimal import Decimal
        from django.db.models import Sum

        restaurant = request.user.restaurant
        today      = timezone.localdate()

        # Caisse Globale active
        caisse_globale = CaisseGlobale.objects.filter(
            restaurant=restaurant, is_closed=False
        ).first()

        # Ma caisse comptable ouverte
        ma_caisse = CaisseComptable.objects.filter(
            comptable=request.user, is_closed=False
        ).first()

        # Remises en attente (non validees sur la caisse globale active)
        remises_en_attente = 0
        if caisse_globale:
            remises_en_attente = RemiseServeur.objects.filter(
                caisse_globale=caisse_globale, valide=False
            ).count()

        # Remises validees aujourd'hui
        remises_today = RemiseServeur.objects.filter(
            caisse_globale__restaurant=restaurant,
            valide=True,
            updated_at__date=today,
        )
        remises_validees_today = remises_today.count()
        total_remises = remises_today.aggregate(
            total=Sum('montant_physique')
        )['total'] or Decimal('0.00')

        # Depenses du jour (sur toutes les caisses comptables ouvertes)
        depenses_today = Depense.objects.filter(
            caisse_comptable__restaurant=restaurant,
            date_depense=today,
        )
        total_depenses = depenses_today.aggregate(
            total=Sum('montant')
        )['total'] or Decimal('0.00')

        data = {
            'caisse_globale_active': (
                CaisseGlobaleSerializer(caisse_globale).data
                if caisse_globale else None
            ),
            'ma_caisse_comptable': (
                CaisseComptableListSerializer(ma_caisse).data
                if ma_caisse else None
            ),
            'remises_en_attente_count': remises_en_attente,
            'remises_validees_today':   remises_validees_today,
            'total_remises_today':      total_remises,
            'total_depenses_today':     total_depenses,
        }
        return ok(data=data, message="Dashboard Comptable.")
