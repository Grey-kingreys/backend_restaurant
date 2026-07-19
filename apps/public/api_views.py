# apps/public/api_views.py
# Endpoints publics pour la vitrine client (commandes livraison / emporter).

import secrets
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.core.validators import EmailValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, OpenApiResponse

from django.utils import timezone
from apps.company.models import Restaurant
from apps.menu.models import Plat
from apps.commandes.models import Commande, CommandeItem, LivraisonToken

User = get_user_model()


def ok(data=None, message="", code=status.HTTP_200_OK):
    from rest_framework.response import Response
    return Response({'success': True, 'data': data, 'message': message}, status=code)


def err(message="Erreur.", code=status.HTTP_400_BAD_REQUEST, errors=None):
    from rest_framework.response import Response
    return Response({'success': False, 'message': message, 'errors': errors}, status=code)


def get_restaurant_by_slug(slug):
    """Retourne le restaurant actif correspondant au slug ou None."""
    try:
        return Restaurant.objects.get(is_active=True, nom__iexact=slug.replace('-', ' '))
    except Restaurant.DoesNotExist:
        pass
    # Deuxième tentative : slug dérivé (lebaobab → Le Baobab)
    for resto in Restaurant.objects.filter(is_active=True):
        if resto.get_slug() == slug:
            return resto
    return None


# ─────────────────────────────────────────────────────────────────────────────
# AUTH CLIENT — Inscription Rclient
# ─────────────────────────────────────────────────────────────────────────────

class ClientRegisterView(APIView):
    """
    POST /api/public/auth/register/
    Inscription d'un nouveau client (Rclient).
    Accès : Public
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Inscription client",
        tags=["Public - Auth"],
    )
    def post(self, request):
        data = request.data
        email        = (data.get('email') or '').strip().lower()
        password     = data.get('password') or ''
        password2    = data.get('password_confirm') or ''
        nom_complet  = (data.get('nom_complet') or '').strip()
        telephone    = (data.get('telephone') or '').strip()

        errors = {}
        if not email:
            errors['email'] = ["L'email est obligatoire."]
        else:
            try:
                EmailValidator()(email)
            except DjangoValidationError:
                errors['email'] = ["Email invalide."]
            else:
                if User.objects.filter(email=email).exists():
                    errors['email'] = ["Un compte avec cet email existe déjà."]

        if not password or len(password) < 8:
            errors['password'] = ["Le mot de passe doit faire au moins 8 caractères."]
        elif password != password2:
            errors['password_confirm'] = ["Les mots de passe ne correspondent pas."]

        if not nom_complet:
            errors['nom_complet'] = ["Le nom complet est obligatoire."]

        if errors:
            return err(message="Données invalides.", errors=errors, code=status.HTTP_400_BAD_REQUEST)

        # Générer un login unique
        base = email.split('@')[0].lower().replace('.', '_')[:20]
        login = base
        n = 1
        while User.objects.filter(login=login).exists():
            login = f"{base}_{n}"
            n += 1

        user = User.objects.create_user(
            login=login,
            email=email,
            password=password,
            nom_complet=nom_complet,
            telephone=telephone or None,
            role='Rclient',
            restaurant=None,
            actif=True,
            must_change_password=False,
        )

        refresh = RefreshToken.for_user(user)
        return ok(
            data={
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'nom_complet': user.nom_complet,
                    'telephone': user.telephone,
                    'role': user.role,
                },
            },
            message="Compte créé avec succès.",
            code=status.HTTP_201_CREATED,
        )


# ─────────────────────────────────────────────────────────────────────────────
# RESTAURANTS PUBLICS
# ─────────────────────────────────────────────────────────────────────────────

class RestaurantListPublicView(APIView):
    """
    GET /api/public/restaurants/
    Liste des restaurants actifs avec livraison ou emporter activé.
    Accès : Public
    """
    permission_classes = [AllowAny]

    @extend_schema(summary="Liste restaurants publics", tags=["Public - Restaurants"])
    def get(self, request):
        restos = Restaurant.objects.filter(
            is_active=True
        ).filter(
            accept_livraison=True
        ) | Restaurant.objects.filter(
            is_active=True
        ).filter(
            accept_emporter=True
        )
        restos = restos.distinct()

        data = [_serialize_restaurant(r) for r in restos]
        return ok(data={'restaurants': data, 'count': len(data)})


class RestaurantDetailPublicView(APIView):
    """
    GET /api/public/restaurants/<slug>/
    Détail restaurant + menu complet (plats disponibles).
    Accès : Public
    """
    permission_classes = [AllowAny]

    @extend_schema(summary="Détail restaurant public + menu", tags=["Public - Restaurants"])
    def get(self, request, slug):
        resto = get_restaurant_by_slug(slug)
        if not resto:
            return err(message="Restaurant introuvable.", code=status.HTTP_404_NOT_FOUND)

        plats = Plat.objects.filter(restaurant=resto, disponible=True).order_by('categorie', 'nom')
        plats_data = [
            {
                'id': p.id,
                'nom': p.nom,
                'description': p.description,
                'prix_unitaire': str(p.prix_unitaire),
                'categorie': p.categorie,
                'image_url': p.image_url or (
                    request.build_absolute_uri(p.image.url) if p.image else None
                ),
                'necessite_validation_cuisine': p.necessite_validation_cuisine,
            }
            for p in plats
        ]

        return ok(data={
            'restaurant': _serialize_restaurant(resto),
            'plats': plats_data,
            'count_plats': len(plats_data),
        })


class PlatsPublicListView(APIView):
    """
    GET /api/public/plats/
    Tous les plats disponibles de tous les restaurants ouverts à la commande en ligne.
    Inclut les infos du restaurant (dont GPS) pour la recherche et la future carte.
    Accès : Public
    """
    permission_classes = [AllowAny]

    @extend_schema(summary="Tous les plats publics", tags=["Public - Restaurants"])
    def get(self, request):
        restos = Restaurant.objects.filter(is_active=True).filter(
            Q(accept_livraison=True) | Q(accept_emporter=True)
        ).distinct()

        plats = (
            Plat.objects
            .filter(disponible=True, restaurant__in=restos)
            .select_related('restaurant')
            .order_by('nom')
        )

        data = [
            {
                'id': p.id,
                'nom': p.nom,
                'description': p.description,
                'prix_unitaire': str(p.prix_unitaire),
                'categorie': p.categorie,
                'image_url': p.image_url or (
                    request.build_absolute_uri(p.image.url) if p.image else None
                ),
                'restaurant': {
                    'nom': p.restaurant.nom,
                    'slug': p.restaurant.get_slug(),
                    'adresse': p.restaurant.adresse,
                    'latitude': str(p.restaurant.latitude) if p.restaurant.latitude else None,
                    'longitude': str(p.restaurant.longitude) if p.restaurant.longitude else None,
                },
            }
            for p in plats
        ]
        return ok(data={'plats': data, 'count': len(data)})


def _serialize_restaurant(r):
    return {
        'id': r.id,
        'nom': r.nom,
        'slug': r.get_slug(),
        'adresse': r.adresse,
        'telephone': r.telephone,
        'latitude': str(r.latitude) if r.latitude else None,
        'longitude': str(r.longitude) if r.longitude else None,
        'accept_livraison': r.accept_livraison,
        'accept_emporter': r.accept_emporter,
        'frais_livraison': str(r.frais_livraison) if r.frais_livraison else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# COMMANDER — Rclient authentifié
# ─────────────────────────────────────────────────────────────────────────────

MODES_PAIEMENT_DISPONIBLES = {'livraison'}  # seul mode actif pour l'instant


class CommanderView(APIView):
    """
    POST /api/public/restaurants/<slug>/commander/
    Crée une commande livraison ou emporter.

    Body:
        type_commande: "livraison" | "emporter"
        mode_paiement: "livraison" | "orange_money" | "mtn" | "carte" | "paydunya"
        adresse_livraison: str (requis si livraison)
        telephone: str
        items: [{plat_id, quantite}]

    Accès : Rclient authentifié
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Créer une commande livraison/emporter", tags=["Public - Commandes"])
    def post(self, request, slug):
        user = request.user
        if user.role != 'Rclient':
            return err(message="Réservé aux clients.", code=status.HTTP_403_FORBIDDEN)

        resto = get_restaurant_by_slug(slug)
        if not resto:
            return err(message="Restaurant introuvable.", code=status.HTTP_404_NOT_FOUND)

        data = request.data
        type_cmd     = data.get('type_commande', 'livraison')
        mode_pmt     = data.get('mode_paiement', 'livraison')
        adresse      = (data.get('adresse_livraison') or '').strip()
        telephone    = (data.get('telephone') or user.telephone or '').strip()
        items        = data.get('items') or []
        # Position choisie sur la carte (optionnelle) — livraison uniquement
        try:
            client_lat = float(data['latitude']) if data.get('latitude') not in (None, '') else None
            client_lng = float(data['longitude']) if data.get('longitude') not in (None, '') else None
        except (TypeError, ValueError, KeyError):
            client_lat = client_lng = None

        # Validations
        errors = {}
        if type_cmd not in ('livraison', 'emporter'):
            errors['type_commande'] = ["Valeur invalide. Choisissez 'livraison' ou 'emporter'."]
        if type_cmd == 'livraison' and not resto.accept_livraison:
            errors['type_commande'] = ["Ce restaurant n'accepte pas les livraisons."]
        if type_cmd == 'emporter' and not resto.accept_emporter:
            errors['type_commande'] = ["Ce restaurant n'accepte pas les commandes à emporter."]
        if type_cmd == 'livraison' and not adresse:
            errors['adresse_livraison'] = ["L'adresse de livraison est obligatoire."]
        if not telephone:
            errors['telephone'] = ["Le numéro de téléphone est obligatoire."]
        if mode_pmt not in [c[0] for c in Commande.MODE_PAIEMENT_CHOICES]:
            errors['mode_paiement'] = ["Mode de paiement invalide."]
        if mode_pmt not in MODES_PAIEMENT_DISPONIBLES:
            errors['mode_paiement'] = [f"Ce mode de paiement n'est pas encore disponible. Choisissez 'livraison'."]
        if not items:
            errors['items'] = ["La commande doit contenir au moins un article."]

        if errors:
            return err(message="Données invalides.", errors=errors)

        # Vérifier et calculer les articles
        montant = 0
        items_valides = []
        for item in items:
            try:
                plat = Plat.objects.get(id=item.get('plat_id'), restaurant=resto, disponible=True)
            except Plat.DoesNotExist:
                return err(message=f"Plat #{item.get('plat_id')} introuvable ou indisponible.")
            qte = max(1, int(item.get('quantite', 1)))
            montant += plat.prix_unitaire * qte
            items_valides.append((plat, qte))

        if type_cmd == 'livraison' and resto.frais_livraison:
            montant += resto.frais_livraison

        # Créer la commande
        cle = secrets.token_hex(16)
        commande = Commande.objects.create(
            restaurant=resto,
            table=user,
            type_commande=type_cmd,
            client_nom=user.nom_complet,
            client_telephone=telephone,
            client_adresse_livraison=adresse if type_cmd == 'livraison' else None,
            client_latitude=client_lat if type_cmd == 'livraison' else None,
            client_longitude=client_lng if type_cmd == 'livraison' else None,
            mode_paiement=mode_pmt,
            montant_total=montant,
            statut='en_attente',
            cle_suivi=cle,
        )
        for plat, qte in items_valides:
            CommandeItem.objects.create(
                commande=commande,
                plat=plat,
                quantite=qte,
                prix_unitaire=plat.prix_unitaire,
            )

        return ok(
            data={
                'commande_id': commande.id,
                'cle_suivi': cle,
                'statut': commande.statut,
                'montant_total': str(commande.montant_total),
                'type_commande': commande.type_commande,
                'mode_paiement': commande.mode_paiement,
                'suivi_url': f"/restaurant/{resto.get_slug()}/confirmation/{cle}/",
            },
            message="Commande passée avec succès !",
            code=status.HTTP_201_CREATED,
        )


# ─────────────────────────────────────────────────────────────────────────────
# MES COMMANDES — Rclient authentifié (historique personnel)
# ─────────────────────────────────────────────────────────────────────────────

class MesCommandesClientView(APIView):
    """
    GET /api/public/mes-commandes/
    Historique des commandes du client connecté + petites stats.
    Accès : Rclient authentifié
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Mes commandes (client)", tags=["Public - Commandes"])
    def get(self, request):
        user = request.user
        if user.role != 'Rclient':
            return err(message="Réservé aux clients.", code=status.HTTP_403_FORBIDDEN)

        commandes = (
            Commande.objects
            .filter(table=user)
            .select_related('restaurant')
            .prefetch_related('items')
            .order_by('-date_commande')
        )

        en_cours_statuts = {'en_attente', 'prete', 'en_livraison', 'servie'}
        data = []
        total_depense = 0
        nb_en_cours = 0
        for cmd in commandes:
            nb_items = sum(i.quantite for i in cmd.items.all())
            if cmd.statut in en_cours_statuts:
                nb_en_cours += 1
            if cmd.statut == 'payee':
                total_depense += cmd.montant_total
            data.append({
                'commande_id': cmd.id,
                'cle_suivi': cmd.cle_suivi,
                'restaurant': cmd.restaurant.nom,
                'restaurant_slug': cmd.restaurant.get_slug(),
                'statut': cmd.statut,
                'statut_label': STATUT_LABELS.get(cmd.statut, cmd.statut),
                'type_commande': cmd.type_commande,
                'mode_paiement': cmd.mode_paiement,
                'montant_total': str(cmd.montant_total),
                'nb_items': nb_items,
                'date_commande': cmd.date_commande.isoformat(),
            })

        return ok(data={
            'commandes': data,
            'stats': {
                'total': len(data),
                'en_cours': nb_en_cours,
                'total_depense': str(total_depense),
            },
        })


# ─────────────────────────────────────────────────────────────────────────────
# RÉSERVATION DE TABLE — Client (Rclient)
# ─────────────────────────────────────────────────────────────────────────────

from datetime import datetime, date as _date, timedelta
from apps.restaurant.models import (
    TableRestaurant, Reservation, ReservationClientBloque, duree_reservation_minutes,
)
from apps.restaurant.services.email_service import (
    send_reservation_client, send_reservation_restaurant,
)

STATUT_RESA_LABELS = dict(Reservation.STATUT_CHOICES)


def _heure_fin_str(heure, duree_minutes):
    fin = datetime.combine(_date.min, heure) + timedelta(minutes=int(duree_minutes or 120))
    return fin.strftime('%H:%M')


def _annulation_possible(r):
    """Le client peut-il encore annuler ? (avant le délai du restaurant)."""
    if r.statut not in ('en_attente', 'confirmee'):
        return False
    delai_h = getattr(r.restaurant, 'reservation_delai_annulation_heures', 2) or 0
    limite = datetime.combine(r.date_reservation, r.heure) - timedelta(hours=delai_h)
    return datetime.now() < limite


def _serialize_reservation(r):
    """Vue CLIENT — sans numéro de table (révélé à l'arrivée)."""
    return {
        'id': r.id,
        'restaurant': r.restaurant.nom,
        'restaurant_slug': r.restaurant.get_slug(),
        'date_reservation': r.date_reservation.isoformat(),
        'heure': r.heure.strftime('%H:%M'),
        'heure_fin': _heure_fin_str(r.heure, r.duree_minutes),
        'duree_minutes': r.duree_minutes,
        'nombre_personnes': r.nombre_personnes,
        'note': r.note,
        'statut': r.statut,
        'statut_label': STATUT_RESA_LABELS.get(r.statut, r.statut),
        'annulable': _annulation_possible(r),
        'delai_annulation_heures': getattr(r.restaurant, 'reservation_delai_annulation_heures', 2),
        'date_creation': r.date_creation.isoformat(),
    }


def _parse_date_heure(date_str, heure_str):
    d = datetime.strptime(date_str, '%Y-%m-%d').date()
    h = datetime.strptime(heure_str, '%H:%M').time()
    return d, h


class TablesDisponiblesView(APIView):
    """
    GET /api/public/restaurants/<slug>/tables/?date=YYYY-MM-DD&heure=HH:MM&personnes=N
    Vérifie s'il reste AU MOINS une table disponible pour le créneau demandé.
    Le client ne choisit plus une table précise : l'attribution est automatique.
    Accès : Public
    """
    permission_classes = [AllowAny]

    @extend_schema(summary="Disponibilité pour réservation", tags=["Public - Réservations"])
    def get(self, request, slug):
        resto = get_restaurant_by_slug(slug)
        if not resto:
            return err(message="Restaurant introuvable.", code=status.HTTP_404_NOT_FOUND)

        try:
            personnes = max(1, int(request.query_params.get('personnes', 1)))
        except (TypeError, ValueError):
            personnes = 1

        date_str = request.query_params.get('date')
        heure_str = request.query_params.get('heure')
        if not (date_str and heure_str):
            return err(message="Date et heure requises.", errors={'date': ["Renseignez date et heure."]})
        try:
            date_resa, heure = _parse_date_heure(date_str, heure_str)
        except ValueError:
            return err(message="Date ou heure invalide.", errors={'date': ["Format attendu AAAA-MM-JJ / HH:MM."]})

        capacite_max = (
            TableRestaurant.objects.filter(restaurant=resto)
            .order_by('-nombre_places').values_list('nombre_places', flat=True).first()
        ) or 0
        table = Reservation.trouver_table_disponible(resto, date_resa, heure, personnes)
        duree = duree_reservation_minutes(personnes)

        if personnes > capacite_max and capacite_max:
            disponible, message = False, f"Aucune table ne peut accueillir {personnes} personnes (max {capacite_max})."
        elif table is None:
            disponible, message = False, "Complet sur ce créneau. Essayez une autre heure."
        else:
            disponible, message = True, "Une table est disponible pour ce créneau."

        return ok(data={
            'disponible': disponible,
            'message': message,
            'duree_minutes': duree,
            'heure_fin': _heure_fin_str(heure, duree),
            'capacite_max': capacite_max,
        })


class ReserverView(APIView):
    """
    POST /api/public/restaurants/<slug>/reserver/
    Body : date (AAAA-MM-JJ), heure (HH:MM), nombre_personnes, note
    Le système attribue automatiquement une table (la plus petite qui convient,
    libre sur le créneau). Confirmation auto ou en attente selon le réglage du resto.
    Accès : Rclient authentifié
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Réserver une table", tags=["Public - Réservations"])
    def post(self, request, slug):
        user = request.user
        if user.role != 'Rclient':
            return err(message="Réservé aux clients.", code=status.HTTP_403_FORBIDDEN)

        resto = get_restaurant_by_slug(slug)
        if not resto:
            return err(message="Restaurant introuvable.", code=status.HTTP_404_NOT_FOUND)

        # Client bloqué par ce restaurant ?
        if ReservationClientBloque.objects.filter(restaurant=resto, client=user).exists():
            return err(
                message="Vous ne pouvez pas réserver dans ce restaurant. Veuillez le contacter directement.",
                code=status.HTTP_403_FORBIDDEN,
            )

        data = request.data
        errors = {}
        try:
            date_resa, heure = _parse_date_heure(data.get('date', ''), data.get('heure', ''))
        except ValueError:
            return err(message="Données invalides.", errors={'date': ["Date/heure invalides (AAAA-MM-JJ, HH:MM)."]})

        if date_resa < _date.today():
            errors['date'] = ["La date de réservation est déjà passée."]

        try:
            personnes = max(1, int(data.get('nombre_personnes', 1)))
        except (TypeError, ValueError):
            personnes = 1

        if errors:
            return err(message="Données invalides.", errors=errors)

        # Attribution automatique de la table
        table = Reservation.trouver_table_disponible(resto, date_resa, heure, personnes)
        if table is None:
            return err(
                message="Aucune table disponible pour ce créneau. Essayez une autre heure ou un autre jour.",
                code=status.HTTP_409_CONFLICT,
            )

        statut = 'confirmee' if resto.reservation_validation_auto else 'en_attente'
        resa = Reservation.objects.create(
            restaurant=resto, table=table, client=user,
            date_reservation=date_resa, heure=heure,
            nombre_personnes=personnes,
            duree_minutes=duree_reservation_minutes(personnes),
            note=(data.get('note') or '').strip(),
            statut=statut,
        )

        # Notifications email (best-effort, n'interrompt jamais la réponse)
        try:
            resa.client_no_show_count = Reservation.no_show_count(user)
            send_reservation_client(resa)
            send_reservation_restaurant(resa)
        except Exception:
            pass

        msg = ("Réservation confirmée. Un email de confirmation vous a été envoyé."
               if statut == 'confirmee'
               else "Réservation envoyée. En attente de confirmation du restaurant.")
        return ok(data=_serialize_reservation(resa), message=msg, code=status.HTTP_201_CREATED)


class MesReservationsView(APIView):
    """GET /api/public/mes-reservations/ — réservations du client connecté."""
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Mes réservations (client)", tags=["Public - Réservations"])
    def get(self, request):
        if request.user.role != 'Rclient':
            return err(message="Réservé aux clients.", code=status.HTTP_403_FORBIDDEN)
        resas = (
            Reservation.objects.filter(client=request.user)
            .select_related('restaurant', 'table')
            .order_by('-date_reservation', '-heure')
        )
        return ok(data={'reservations': [_serialize_reservation(r) for r in resas], 'count': resas.count()})


class AnnulerReservationView(APIView):
    """POST /api/public/reservations/<pk>/annuler/ — le client annule sa réservation."""
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Annuler une réservation", tags=["Public - Réservations"])
    def post(self, request, pk):
        try:
            resa = Reservation.objects.get(pk=pk, client=request.user)
        except Reservation.DoesNotExist:
            return err(message="Réservation introuvable.", code=status.HTTP_404_NOT_FOUND)
        if resa.statut not in ('en_attente', 'confirmee'):
            return err(message="Cette réservation ne peut plus être annulée.")
        if not _annulation_possible(resa):
            delai = getattr(resa.restaurant, 'reservation_delai_annulation_heures', 2)
            return err(
                message=f"Le délai d'annulation ({delai}h avant) est dépassé. "
                        f"Merci de contacter directement le restaurant.",
                code=status.HTTP_409_CONFLICT,
            )
        resa.statut = 'annulee'
        resa.save(update_fields=['statut', 'date_modification'])
        return ok(data=_serialize_reservation(resa), message="Réservation annulée.")


# ─────────────────────────────────────────────────────────────────────────────
# SUIVI COMMANDE — Public (clé de suivi)
# ─────────────────────────────────────────────────────────────────────────────

STATUT_LABELS = {
    'en_attente':   'Commande reçue',
    'prete':        'En préparation terminée',
    'en_livraison': 'En cours de livraison',
    'servie':       'Livrée / Servie',
    'payee':        'Payée',
}

STATUT_STEPS = ['en_attente', 'prete', 'en_livraison', 'servie', 'payee']


class SuiviCommandeView(APIView):
    """
    GET /api/public/commandes/<cle_suivi>/
    Suivi de commande via la clé publique (pas d'auth requise).
    Accès : Public
    """
    permission_classes = [AllowAny]

    @extend_schema(summary="Suivi commande client", tags=["Public - Commandes"])
    def get(self, request, cle_suivi):
        try:
            cmd = Commande.objects.select_related('restaurant').get(cle_suivi=cle_suivi)
        except Commande.DoesNotExist:
            return err(message="Commande introuvable.", code=status.HTTP_404_NOT_FOUND)

        # Étapes réellement suivies par CETTE commande :
        #   - EN_LIVRAISON seulement pour les livraisons ;
        #   - PRETE seulement si un plat passe par la cuisine.
        necessite_cuisine = cmd.necessite_passage_cuisine()
        steps = list(STATUT_STEPS)
        if cmd.type_commande != 'livraison':
            steps = [s for s in steps if s != 'en_livraison']
        if not necessite_cuisine:
            steps = [s for s in steps if s != 'prete']
        current_index = steps.index(cmd.statut) if cmd.statut in steps else 0

        items = [
            {
                'nom': i.plat.nom,
                'quantite': i.quantite,
                'prix_unitaire': str(i.prix_unitaire),
                'sous_total': str(i.quantite * i.prix_unitaire),
            }
            for i in cmd.items.select_related('plat').all()
        ]

        return ok(data={
            'commande_id': cmd.id,
            'restaurant': cmd.restaurant.nom,
            'statut': cmd.statut,
            'statut_label': STATUT_LABELS.get(cmd.statut, cmd.statut),
            'statut_index': current_index,
            'statut_total': len(steps),
            'necessite_passage_cuisine': necessite_cuisine,
            'type_commande': cmd.type_commande,
            'mode_paiement': cmd.mode_paiement,
            'montant_total': str(cmd.montant_total),
            'frais_livraison': str(cmd.restaurant.frais_livraison) if cmd.restaurant.frais_livraison else None,
            'adresse_livraison': cmd.client_adresse_livraison,
            'date_commande': cmd.date_commande.isoformat(),
            'items': items,
        })


# ─────────────────────────────────────────────────────────────────────────────
# LIVRAISON EXTERNE — Public (token de livraison)
# ─────────────────────────────────────────────────────────────────────────────

def _serialize_livraison_publique(cmd):
    """Vue livreur externe : coordonnées client + articles + actions autorisées."""
    resto = cmd.restaurant
    paiement_autorise = resto.livraison_lien_autorise_paiement
    return {
        'commande_id': cmd.id,
        'restaurant': resto.nom,
        'restaurant_telephone': resto.telephone,
        'statut': cmd.statut,
        'statut_label': STATUT_LABELS.get(cmd.statut, cmd.statut),
        'client_nom': cmd.client_nom,
        'client_telephone': cmd.client_telephone,
        'adresse_livraison': cmd.client_adresse_livraison,
        'latitude': str(cmd.client_latitude) if cmd.client_latitude is not None else None,
        'longitude': str(cmd.client_longitude) if cmd.client_longitude is not None else None,
        'mode_paiement': cmd.mode_paiement,
        'montant_total': str(cmd.montant_total),
        'items': [
            {
                'nom': i.plat.nom,
                'quantite': i.quantite,
                'sous_total': str(i.quantite * i.prix_unitaire),
            }
            for i in cmd.items.select_related('plat').all()
        ],
        'paiement_autorise': paiement_autorise,
        'actions': {
            'peut_passer_en_livraison': cmd.peut_passer_en_livraison(),
            'peut_etre_servie': cmd.peut_etre_servie(),
            'peut_encaisser': bool(paiement_autorise and cmd.peut_etre_payee()),
        },
    }


class LivraisonPubliqueView(APIView):
    """
    GET /api/public/livraison/<token>/
    Vue publique d'une commande de livraison pour un livreur externe (sans compte).
    Accès : Public (token).
    """
    permission_classes = [AllowAny]

    @extend_schema(summary="Livraison externe — détail", tags=["Public - Livraison"])
    def get(self, request, token):
        try:
            lt = LivraisonToken.objects.select_related('commande', 'commande__restaurant').get(token=token)
        except LivraisonToken.DoesNotExist:
            return err(message="Lien de livraison invalide ou expiré.", code=status.HTTP_404_NOT_FOUND)
        return ok(data=_serialize_livraison_publique(lt.commande))


class LivraisonPubliqueActionView(APIView):
    """
    POST /api/public/livraison/<token>/action/   body: {"action": "en_livraison" | "servie" | "payee"}
    Le livreur externe fait avancer la commande. L'encaissement ('payee') n'est
    possible que si le restaurant l'autorise ; il est attribué au créateur du lien.
    Accès : Public (token).
    """
    permission_classes = [AllowAny]

    @extend_schema(summary="Livraison externe — action", tags=["Public - Livraison"])
    def post(self, request, token):
        try:
            lt = LivraisonToken.objects.select_related('commande', 'commande__restaurant', 'cree_par').get(token=token)
        except LivraisonToken.DoesNotExist:
            return err(message="Lien de livraison invalide ou expiré.", code=status.HTTP_404_NOT_FOUND)

        cmd = lt.commande
        action = (request.data.get('action') or '').strip()

        if action == 'en_livraison':
            if not cmd.peut_passer_en_livraison():
                return err(message="La commande n'est pas prête à partir en livraison.")
            cmd.statut = 'en_livraison'
            cmd.save(update_fields=['statut', 'date_modification'])

        elif action == 'servie':
            if not cmd.peut_etre_servie():
                return err(message="La commande doit d'abord être en cours de livraison.")
            cmd.statut = 'servie'
            cmd.save(update_fields=['statut', 'date_modification'])

        elif action == 'payee':
            if not cmd.restaurant.livraison_lien_autorise_paiement:
                return err(message="L'encaissement par lien n'est pas autorisé par le restaurant.", code=status.HTTP_403_FORBIDDEN)
            if not cmd.peut_etre_payee():
                return err(message="La commande doit d'abord être livrée.")
            from apps.commandes.serializers import CommandePayeeSerializer
            s = CommandePayeeSerializer(data={}, context={'commande': cmd})
            if not s.is_valid():
                return err(errors=s.errors, message="Encaissement impossible.")
            cmd = s.save(serveur=lt.cree_par)  # remise attribuée au responsable du lien

        else:
            return err(message="Action inconnue.")

        lt.date_derniere_utilisation = timezone.now()
        lt.save(update_fields=['date_derniere_utilisation'])
        return ok(data=_serialize_livraison_publique(cmd), message="Commande mise à jour.")
