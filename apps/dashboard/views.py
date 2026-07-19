from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from django.db.models import Sum, Count
from django.db.models.functions import ExtractHour
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from apps.accounts.api_views import success_response
from apps.accounts.permissions import IsRestaurantActive
from apps.commandes.models import Commande, CommandeItem
from apps.paiements.models import Paiement, Depense, RemiseServeur
from apps.restaurant.models import TableRestaurant

# Noms lisibles pour les catégories
CAT_LABELS = {
    'ENTREE': 'Entrée',
    'PLAT': 'Plat principal',
    'DESSERT': 'Dessert',
    'BOISSON': 'Boisson',
    'ACCOMPAGNEMENT': 'Accompagnement',
}


class DashboardView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurantActive]

    def get(self, request):
        user       = request.user
        restaurant = user.restaurant

        # Utiliser dashboard_type depuis role_config si disponible, sinon fallback sur role
        if user.role_config_id:
            dtype = user.role_config.dashboard_type
        elif user.is_super_admin():
            dtype = 'superadmin'
        elif user.is_table():
            dtype = 'table'
        else:
            dtype = None

        if dtype == 'admin':
            return self._dashboard_admin(request, restaurant)
        if dtype == 'serveur':
            return self._dashboard_serveur(request, restaurant)
        if dtype == 'cuisine':
            return self._dashboard_cuisine(request, restaurant)
        if dtype == 'comptable':
            return self._dashboard_comptable(request, restaurant)
        if dtype == 'livreur':
            return self._dashboard_livreur(request, restaurant)
        if dtype == 'table':
            return self._dashboard_table(request)
        return self._dashboard_superadmin()

    # ── Admin / Manager ────────────────────────────────────────────────────────

    def _dashboard_admin(self, request, restaurant):
        today = timezone.localdate()

        # ── KPIs du jour ──
        revenus_jour = (
            Paiement.objects
            .filter(commande__restaurant=restaurant, date_paiement__date=today)
            .aggregate(total=Sum('montant'))['total'] or Decimal('0')
        )
        commandes_jour = Commande.objects.filter(
            restaurant=restaurant, statut='payee', date_paiement__date=today
        ).count()
        ticket_moyen = (
            (revenus_jour / Decimal(commandes_jour)).quantize(Decimal('0.00'))
            if commandes_jour else Decimal('0.00')
        )
        depenses_jour = (
            Depense.objects
            .filter(caisse_comptable__restaurant=restaurant, date_depense=today)
            .aggregate(total=Sum('montant'))['total'] or Decimal('0')
        )
        commandes_en_attente = Commande.objects.filter(
            restaurant=restaurant, statut='en_attente'
        ).count()
        commandes_pretes = Commande.objects.filter(
            restaurant=restaurant, statut='prete'
        ).count()
        tables_total = TableRestaurant.objects.filter(restaurant=restaurant).count()
        tables_occupees = TableRestaurant.objects.filter(
            restaurant=restaurant,
            utilisateur__commandes__statut__in=['en_attente', 'prete', 'servie']
        ).distinct().count()

        # ── Revenus 7j ──
        revenus_7j = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            rev = (
                Paiement.objects
                .filter(commande__restaurant=restaurant, date_paiement__date=day)
                .aggregate(total=Sum('montant'))['total'] or Decimal('0')
            )
            cmds = Commande.objects.filter(
                restaurant=restaurant, statut='payee', date_paiement__date=day
            ).count()
            revenus_7j.append({'date': day.strftime('%d/%m'), 'revenus': float(rev), 'commandes': cmds})

        # ── Distribution statuts actifs (donut) ──
        statuts_qs = (
            Commande.objects
            .filter(restaurant=restaurant)
            .values('statut')
            .annotate(total=Count('id'))
        )
        statuts_live = [
            {'statut': s['statut'], 'total': s['total'], 'label': {
                'en_attente': 'En attente', 'prete': 'Prête',
                'servie': 'Servie', 'payee': 'Payée'
            }.get(s['statut'], s['statut'])}
            for s in statuts_qs
        ]

        # ── Répartition par catégorie (7j, donut) ──
        par_categorie = list(
            CommandeItem.objects
            .filter(
                commande__restaurant=restaurant,
                commande__date_commande__date__gte=today - timedelta(days=7),
            )
            .values('plat__categorie')
            .annotate(total=Sum('quantite'))
            .order_by('-total')
        )
        par_categorie_data = [
            {'categorie': p['plat__categorie'], 'label': CAT_LABELS.get(p['plat__categorie'], p['plat__categorie']), 'total': p['total']}
            for p in par_categorie
        ]

        # ── Activité par heure (7j) ──
        par_heure_qs = (
            Commande.objects
            .filter(
                restaurant=restaurant,
                date_commande__date__gte=today - timedelta(days=7),
            )
            .annotate(h=ExtractHour('date_commande'))
            .values('h')
            .annotate(n=Count('id'))
        )
        heure_map = {item['h']: item['n'] for item in par_heure_qs}
        par_heure = [{'h': f'{h:02d}h', 'n': heure_map.get(h, 0)} for h in range(6, 23)]

        # ── Top plats (7j) ──
        top_plats = (
            CommandeItem.objects
            .filter(
                commande__restaurant=restaurant,
                commande__date_commande__date__gte=today - timedelta(days=7),
            )
            .values('plat__nom', 'plat__categorie')
            .annotate(total=Sum('quantite'))
            .order_by('-total')[:6]
        )

        # ── Caisse générale ──
        try:
            solde_generale = str(restaurant.caisse_generale.solde)
        except Exception:
            solde_generale = '0.00'

        # ── Dernières commandes ──
        dernieres = (
            Commande.objects.filter(restaurant=restaurant)
            .select_related('table', 'table__table_restaurant')
            .order_by('-date_commande')[:8]
        )

        return success_response(data={
            'type': 'admin',
            'kpis': {
                'revenus_jour': str(revenus_jour),
                'commandes_jour': commandes_jour,
                'ticket_moyen': str(ticket_moyen),
                'tables_occupees': tables_occupees,
                'tables_total': tables_total,
                'commandes_en_attente': commandes_en_attente,
                'commandes_pretes': commandes_pretes,
                'depenses_jour': str(depenses_jour),
                'benefice_net': str(revenus_jour - depenses_jour),
                'solde_generale': solde_generale,
            },
            'revenus_7j': revenus_7j,
            'statuts_live': statuts_live,
            'par_categorie': par_categorie_data,
            'par_heure': par_heure,
            'top_plats': [
                {'nom': p['plat__nom'], 'categorie': p['plat__categorie'], 'total': p['total']}
                for p in top_plats
            ],
            'dernieres_commandes': [_fmt_commande(c) for c in dernieres],
        })

    # ── Serveur ────────────────────────────────────────────────────────────────

    def _dashboard_serveur(self, request, restaurant):
        today = timezone.localdate()

        tables_actives = (
            Commande.objects
            .filter(restaurant=restaurant, statut__in=['en_attente', 'prete', 'servie'])
            .select_related('table', 'table__table_restaurant')
            .order_by('-date_commande')
        )
        pretes_qs = tables_actives.filter(statut='prete')

        # Remises du jour
        remises_jour = (
            RemiseServeur.objects
            .filter(paiement__commande__restaurant=restaurant, serveur=request.user, created_at__date=today)
            .aggregate(total=Sum('montant_virtuel'))['total'] or Decimal('0')
        )

        # Commandes traitées (servie + payée) sur 7 jours
        commandes_traitees_7j = Commande.objects.filter(
            restaurant=restaurant,
            statut__in=['servie', 'payee'],
            date_commande__date__gte=today - timedelta(days=7),
        ).count()

        # Activité par heure sur 7 jours
        par_heure_qs = (
            Commande.objects
            .filter(restaurant=restaurant, date_commande__date__gte=today - timedelta(days=7))
            .annotate(h=ExtractHour('date_commande'))
            .values('h').annotate(n=Count('id'))
        )
        heure_map = {item['h']: item['n'] for item in par_heure_qs}
        par_heure = [{'h': f'{h:02d}h', 'n': heure_map.get(h, 0)} for h in range(6, 23)]

        # Statuts des tables (pour barre d'état)
        tables_all = TableRestaurant.objects.filter(restaurant=restaurant)
        tables_statuts = []
        for t in tables_all:
            statut = t.get_statut_actuel()
            tables_statuts.append({'numero': t.numero_table, 'places': t.nombre_places, 'statut': statut})

        # Revenus générés par les commandes actives
        revenus_actifs = (
            Commande.objects
            .filter(restaurant=restaurant, statut__in=['en_attente', 'prete', 'servie'])
            .aggregate(total=Sum('montant_total'))['total'] or Decimal('0')
        )

        return success_response(data={
            'type': 'serveur',
            'tables_actives': [_fmt_commande(c) for c in tables_actives],
            'commandes_pretes': [_fmt_commande(c) for c in pretes_qs],
            'nb_tables_actives': tables_actives.count(),
            'nb_commandes_pretes': pretes_qs.count(),
            'remises_jour': str(remises_jour),
            'commandes_traitees_7j': commandes_traitees_7j,
            'par_heure': par_heure,
            'tables_statuts': tables_statuts,
            'revenus_actifs': str(revenus_actifs),
        })

    # ── Livreur ────────────────────────────────────────────────────────────────

    def _dashboard_livreur(self, request, restaurant):
        today = timezone.localdate()

        actives = list(
            Commande.objects
            .filter(restaurant=restaurant, type_commande='livraison',
                    statut__in=['en_attente', 'prete', 'en_livraison'])
            .order_by('date_commande')
        )
        en_cours   = sum(1 for c in actives if c.statut == 'en_livraison')
        a_expedier = len(actives) - en_cours
        livrees_jour = Commande.objects.filter(
            restaurant=restaurant, type_commande='livraison',
            statut__in=['servie', 'payee'], date_commande__date=today,
        ).count()

        def fmt(c):
            return {
                'id': c.id,
                'client': c.client_nom or '—',
                'adresse': c.client_adresse_livraison or '',
                'montant': str(c.montant_total),
                'statut': c.statut,
                'heure': c.date_commande.strftime('%H:%M'),
            }

        return success_response(data={
            'type': 'livreur',
            'kpis': {
                'a_expedier': a_expedier,
                'en_cours': en_cours,
                'livrees_jour': livrees_jour,
            },
            'livraisons': [fmt(c) for c in actives[:20]],
        })

    # ── Cuisine ────────────────────────────────────────────────────────────────

    def _dashboard_cuisine(self, request, restaurant):
        is_chef = request.user.role == 'Rchef_cuisinier'
        statuts = ['en_attente', 'prete'] if is_chef else ['en_attente']
        today = timezone.localdate()

        file_commandes = (
            Commande.objects
            .filter(restaurant=restaurant, statut__in=statuts)
            .prefetch_related('items__plat')
            .select_related('table', 'table__table_restaurant')
            .order_by('date_commande')
        )

        # Top plats du jour
        top_plats = (
            CommandeItem.objects
            .filter(commande__restaurant=restaurant, commande__date_commande__date=today)
            .values('plat__nom').annotate(total=Sum('quantite')).order_by('-total')[:5]
        )

        # Répartition par catégorie (7j)
        par_categorie = list(
            CommandeItem.objects
            .filter(commande__restaurant=restaurant, commande__date_commande__date__gte=today - timedelta(days=7))
            .values('plat__categorie').annotate(total=Sum('quantite')).order_by('-total')
        )
        par_categorie_data = [
            {'categorie': p['plat__categorie'], 'label': CAT_LABELS.get(p['plat__categorie'], p['plat__categorie']), 'total': p['total']}
            for p in par_categorie
        ]

        # Activité par heure (7j)
        par_heure_qs = (
            Commande.objects
            .filter(restaurant=restaurant, date_commande__date__gte=today - timedelta(days=7))
            .annotate(h=ExtractHour('date_commande'))
            .values('h').annotate(n=Count('id'))
        )
        heure_map = {item['h']: item['n'] for item in par_heure_qs}
        par_heure = [{'h': f'{h:02d}h', 'n': heure_map.get(h, 0)} for h in range(6, 23)]

        # Total plats servis (7j)
        total_plats_7j = (
            CommandeItem.objects
            .filter(commande__restaurant=restaurant, commande__date_commande__date__gte=today - timedelta(days=7))
            .aggregate(total=Sum('quantite'))['total'] or 0
        )

        # Commande la plus ancienne en attente (pour urgence)
        oldest = (
            Commande.objects
            .filter(restaurant=restaurant, statut='en_attente')
            .order_by('date_commande')
            .first()
        )
        oldest_mins = None
        if oldest:
            delta = timezone.now() - oldest.date_commande
            oldest_mins = int(delta.total_seconds() / 60)

        file_data = []
        for c in file_commandes:
            d = _fmt_commande(c)
            d['items'] = [{'plat': it.plat.nom, 'quantite': it.quantite} for it in c.items.all()]
            # Temps d'attente en minutes
            delta = timezone.now() - c.date_commande
            d['attente_mins'] = int(delta.total_seconds() / 60)
            file_data.append(d)

        return success_response(data={
            'type': 'cuisine',
            'file_commandes': file_data,
            'nb_en_attente': sum(1 for c in file_data if c['statut'] == 'en_attente'),
            'nb_pretes': sum(1 for c in file_data if c['statut'] == 'prete'),
            'top_plats_jour': [{'nom': p['plat__nom'], 'total': p['total']} for p in top_plats],
            'par_categorie': par_categorie_data,
            'par_heure': par_heure,
            'total_plats_7j': total_plats_7j,
            'oldest_wait_mins': oldest_mins,
        })

    # ── Comptable ──────────────────────────────────────────────────────────────

    def _dashboard_comptable(self, request, restaurant):
        from apps.paiements.models import CaisseComptable
        today = timezone.localdate()

        caisse = CaisseComptable.objects.filter(
            restaurant=restaurant, comptable=request.user, is_closed=False
        ).first()

        remises_attente = RemiseServeur.objects.filter(
            caisse_globale__restaurant=restaurant, valide=False
        ).count()

        depenses_jour = (
            Depense.objects
            .filter(caisse_comptable__restaurant=restaurant, date_depense=today)
            .aggregate(total=Sum('montant'))['total'] or Decimal('0')
        )
        revenus_jour = (
            Paiement.objects
            .filter(commande__restaurant=restaurant, date_paiement__date=today)
            .aggregate(total=Sum('montant'))['total'] or Decimal('0')
        )

        # Balance revenus vs dépenses sur 7j
        balance_7j = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            rev = (
                Paiement.objects
                .filter(commande__restaurant=restaurant, date_paiement__date=day)
                .aggregate(total=Sum('montant'))['total'] or Decimal('0')
            )
            dep = (
                Depense.objects
                .filter(caisse_comptable__restaurant=restaurant, date_depense=day)
                .aggregate(total=Sum('montant'))['total'] or Decimal('0')
            )
            balance_7j.append({'date': day.strftime('%d/%m'), 'revenus': float(rev), 'depenses': float(dep)})

        # Solde caisse générale
        try:
            solde_generale = str(restaurant.caisse_generale.solde)
        except Exception:
            solde_generale = '0.00'

        # Dernières remises
        dernieres_remises = (
            RemiseServeur.objects
            .filter(caisse_globale__restaurant=restaurant)
            .select_related('serveur', 'paiement__commande__table__table_restaurant')
            .order_by('-created_at')[:6]
        )
        remises_data = []
        for r in dernieres_remises:
            try:
                table_label = f"Table {r.paiement.commande.table.table_restaurant.numero_table}"
            except Exception:
                table_label = "—"
            remises_data.append({
                'id': r.id,
                'montant': str(r.montant_virtuel),
                'valide': r.valide,
                'table': table_label,
                'serveur': r.serveur.nom_complet or r.serveur.login if r.serveur else "—",
                'date': r.created_at.strftime('%d/%m %H:%M'),
            })

        # Nb commandes payées aujourd'hui
        cmds_payees_jour = Commande.objects.filter(
            restaurant=restaurant, statut='payee', date_paiement__date=today
        ).count()

        return success_response(data={
            'type': 'comptable',
            'caisse': {
                'solde': str(caisse.solde) if caisse else '0.00',
                'is_open': caisse is not None,
                'opened_at': caisse.opened_at.strftime('%H:%M') if caisse else None,
            },
            'remises_en_attente': remises_attente,
            'depenses_jour': str(depenses_jour),
            'revenus_jour': str(revenus_jour),
            'benefice_net': str(revenus_jour - depenses_jour),
            'cmds_payees_jour': cmds_payees_jour,
            'solde_generale': solde_generale,
            'balance_7j': balance_7j,
            'dernieres_remises': remises_data,
        })

    # ── Table ──────────────────────────────────────────────────────────────────

    def _dashboard_table(self, request):
        from apps.menu.models import Plat
        restaurant = request.user.restaurant

        commande_active = (
            Commande.objects
            .filter(table=request.user, statut__in=['en_attente', 'prete', 'servie'])
            .prefetch_related('items__plat')
            .order_by('-date_commande')
            .first()
        )

        # Suggestions : plats populaires du restaurant (uniquement ceux encore disponibles)
        top_plats = (
            CommandeItem.objects
            .filter(commande__restaurant=restaurant, plat__disponible=True)
            .values('plat__id', 'plat__nom', 'plat__categorie', 'plat__prix_unitaire')
            .annotate(total=Sum('quantite'))
            .order_by('-total')[:4]
        )

        # Nombre de plats disponibles
        nb_plats = Plat.objects.filter(restaurant=restaurant, disponible=True).count()

        data = None
        if commande_active:
            delta = timezone.now() - commande_active.date_commande
            data = {
                'id': commande_active.id,
                'statut': commande_active.statut,
                'montant': str(commande_active.montant_total),
                'heure': commande_active.date_commande.strftime('%H:%M'),
                'attente_mins': int(delta.total_seconds() / 60),
                'items': [
                    {'plat': it.plat.nom, 'quantite': it.quantite, 'prix': str(it.prix_unitaire)}
                    for it in commande_active.items.all()
                ],
            }

        return success_response(data={
            'type': 'table',
            'commande_active': data,
            'nb_plats_disponibles': nb_plats,
            'suggestions': [
                {
                    'id': p['plat__id'],
                    'nom': p['plat__nom'],
                    'categorie': p['plat__categorie'],
                    'prix': str(p['plat__prix_unitaire']),
                    'commandes': p['total'],
                }
                for p in top_plats
            ],
        })

    # ── Super Admin ────────────────────────────────────────────────────────────

    def _dashboard_superadmin(self):
        from apps.company.models import Restaurant
        from apps.accounts.models import User

        today = timezone.localdate()
        restaurants = Restaurant.objects.filter(is_active=True)
        total_restaurants = restaurants.count()
        total_users = User.objects.exclude(role='Rsuper_admin').count()

        revenus_global = (
            Paiement.objects
            .filter(date_paiement__date=today)
            .aggregate(total=Sum('montant'))['total'] or Decimal('0')
        )
        commandes_global = Commande.objects.filter(statut='payee', date_paiement__date=today).count()

        # Revenus par restaurant (7j)
        revenus_7j = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            rev = (
                Paiement.objects
                .filter(date_paiement__date=day)
                .aggregate(total=Sum('montant'))['total'] or Decimal('0')
            )
            revenus_7j.append({'date': day.strftime('%d/%m'), 'revenus': float(rev)})

        # Stats par restaurant
        stats_restaurants = []
        for r in restaurants:
            rev = (
                Paiement.objects
                .filter(commande__restaurant=r, date_paiement__date=today)
                .aggregate(total=Sum('montant'))['total'] or Decimal('0')
            )
            actifs = Commande.objects.filter(
                restaurant=r, statut__in=['en_attente', 'prete', 'servie']
            ).count()
            stats_restaurants.append({
                'nom': r.nom,
                'revenus_jour': str(rev),
                'commandes_actives': actifs,
            })

        return success_response(data={
            'type': 'superadmin',
            'total_restaurants': total_restaurants,
            'total_users': total_users,
            'revenus_global_jour': str(revenus_global),
            'commandes_global_jour': commandes_global,
            'revenus_7j': revenus_7j,
            'stats_restaurants': stats_restaurants,
        })


# ── Helper ─────────────────────────────────────────────────────────────────────

def _fmt_commande(c):
    try:
        label = f"Table {c.table.table_restaurant.numero_table}"
    except Exception:
        label = c.table.login
    return {
        'id': c.id,
        'table': label,
        'montant': str(c.montant_total),
        'statut': c.statut,
        'heure': c.date_commande.strftime('%H:%M'),
    }
