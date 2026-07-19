# apps/company/management/commands/seed_demo.py
"""
Seed de démonstration — idempotent.
Insère restaurants, utilisateurs, plats, tables, caisses et 7 jours de
commandes fictives avec des dates relatives à aujourd'hui.
Si les données sont déjà présentes, la commande s'arrête sans erreur.
"""
from datetime import timedelta, datetime as _dt, time as _t
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    help = "Insère les données de démo si elles ne sont pas encore présentes."

    def handle(self, *args, **options):
        from apps.company.models import Restaurant

        if Restaurant.objects.filter(nom="Le Baobab").exists():
            self.stdout.write(self.style.WARNING(
                "✓ Seed déjà présent — aucune modification."
            ))
            return

        self.stdout.write("  Création des données de démo...")
        try:
            with transaction.atomic():
                self._seed()
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"✗ Erreur lors du seed : {exc}"))
            raise

        self.stdout.write(self.style.SUCCESS("✓ Seed terminé avec succès."))

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _dt(day, h, m=0):
        """Construit un datetime timezone-aware à partir d'un objet date + heure."""
        return timezone.make_aware(_dt.combine(day, _t(h, m)))

    # ── seed principal ────────────────────────────────────────────────────────

    def _seed(self):
        from apps.company.models import Restaurant
        from apps.accounts.models import User, RoleConfig
        from apps.menu.models import Plat
        from apps.restaurant.models import TableRestaurant
        from apps.commandes.models import Commande, CommandeItem
        from apps.paiements.models import (
            CaisseGenerale, CaisseGlobale, CaisseComptable,
            Paiement, RemiseServeur, Depense, MouvementCaisse,
        )

        today = timezone.now().date()

        # ── Restaurants ───────────────────────────────────────────────────────
        r1 = Restaurant.objects.create(
            nom="Le Baobab",
            email_admin="ibrahima.diallo@lebaobab.gn",
            telephone="+224620000001",
            adresse="Commune de Kaloum, Conakry",
            latitude=9.509200,
            longitude=-13.712200,
            is_active=True,
            accept_livraison=True,
            accept_emporter=True,
            frais_livraison=15000,
        )
        r2 = Restaurant.objects.create(
            nom="Chez Mariama",
            email_admin="mariama.balde@chezmariama.gn",
            telephone="+224621000002",
            adresse="Dixinn, Conakry",
            latitude=9.537000,
            longitude=-13.678500,
            is_active=True,
            accept_livraison=False,
            accept_emporter=True,
        )

        # ── Utilisateurs ─────────────────────────────────────────────────────
        # Cache des RoleConfig système pour éviter N requêtes
        _role_config_cache = {
            rc.slug: rc
            for rc in RoleConfig.objects.filter(is_system=True)
        }

        def mkuser(login, role, resto, nom=None, email=None, tel=None,
                   is_staff=False, must_change=False):
            u = User(
                login=login,
                role=role,
                restaurant=resto,
                nom_complet=nom,
                email=email,
                telephone=tel,
                is_staff=is_staff,
                actif=True,
                must_change_password=must_change,
                role_config=_role_config_cache.get(role),
            )
            u.set_password("Soul2001")
            u.save()
            return u

        # Superadmin (sans restaurant)
        u_super = User(
            login="superadmin",
            role="Rsuper_admin",
            restaurant=None,
            nom_complet="Administrateur Plateforme",
            email="admin@restopro.gn",
            is_staff=True,
            is_superuser=True,
            actif=True,
            must_change_password=False,
        )
        u_super.set_password("Soul2001")
        u_super.save()

        # Le Baobab
        u_admin    = mkuser("lebaobab_admin",    "Radmin",          r1, "Ibrahima Diallo",   "ibrahima.diallo@lebaobab.gn",    "+224620100001", is_staff=True)
        u_manager  = mkuser("lebaobab_manager",  "Rmanager",        r1, "Fatoumata Camara",  "fatoumata.camara@lebaobab.gn",   "+224620100002")
        u_serveur  = mkuser("lebaobab_serveur",  "Rserveur",        r1, "Mamadou Bah",       "mamadou.bah@lebaobab.gn",        "+224620100003")
        u_chef     = mkuser("lebaobab_chef",     "Rchef_cuisinier", r1, "Oumar Kouyaté",     "oumar.kouyate@lebaobab.gn",      "+224620100004")
        u_cuis     = mkuser("lebaobab_cuisinier","Rcuisinier",      r1, "Sekou Traoré",      "sekou.traore@lebaobab.gn",       "+224620100005")
        u_cpt      = mkuser("lebaobab_comptable","Rcomptable",      r1, "Aissatou Sow",      "aissatou.sow@lebaobab.gn",       "+224620100006")
        u_livreur  = mkuser("lebaobab_livreur",  "Rlivreur",        r1, "Thierno Barry",     "thierno.barry@lebaobab.gn",      "+224620100007")
        u_t1       = mkuser("lebaobab_table_01", "Rtable",          r1)
        u_t2       = mkuser("lebaobab_table_02", "Rtable",          r1)
        u_t3       = mkuser("lebaobab_table_03", "Rtable",          r1)
        u_t4       = mkuser("lebaobab_table_04", "Rtable",          r1)

        # Chez Mariama
        mkuser("chezmariama_admin",    "Radmin",    r2, "Mariama Baldé", "mariama.balde@chezmariama.gn", "+224621000010", is_staff=True)
        mkuser("chezmariama_comptable","Rcomptable",r2, "Alpha Barry",   "alpha.barry@chezmariama.gn",   "+224621000011")

        # ── Plats Le Baobab ───────────────────────────────────────────────────
        # Images de démo (loremflickr, par mot-clé, déterministes via lock)
        PLAT_IMAGES = {
            "Thiéboudienne":       "https://loremflickr.com/600/400/rice,fish?lock=11",
            "Poulet Yassa":        "https://loremflickr.com/600/400/chicken?lock=22",
            "Salade César":        "https://loremflickr.com/600/400/salad?lock=33",
            "Jus de Bissap":       "https://loremflickr.com/600/400/juice?lock=44",
            "Beignets de banane":  "https://loremflickr.com/600/400/donuts?lock=55",
            "Riz blanc":           "https://loremflickr.com/600/400/rice?lock=66",
            "Soupe de Légumes":    "https://loremflickr.com/600/400/soup?lock=77",
            "Eau minérale":        "https://loremflickr.com/600/400/water,bottle?lock=88",
            "Thiébou Djeun Blanc": "https://loremflickr.com/600/400/fish,rice?lock=99",
            "Jus Gingembre":       "https://loremflickr.com/600/400/ginger,tea?lock=101",
            "Mafé Bœuf":           "https://loremflickr.com/600/400/beef,stew?lock=111",
            "Ginger frais":        "https://loremflickr.com/600/400/ginger,juice?lock=121",
        }

        def plat(resto, nom, desc, prix, cat, cuisine=False, dispo=True):
            return Plat.objects.create(
                restaurant=resto, nom=nom, description=desc,
                prix_unitaire=Decimal(str(prix)), categorie=cat,
                necessite_validation_cuisine=cuisine, disponible=dispo,
                image_url=PLAT_IMAGES.get(nom, ""),
            )

        p1  = plat(r1, "Thiéboudienne",       "Riz au poisson sénégalais",            45000, "PLAT",           cuisine=True)
        p2  = plat(r1, "Poulet Yassa",        "Poulet mariné aux oignons et citron",  40000, "PLAT",           cuisine=True)
        p3  = plat(r1, "Salade César",        "Salade romaine, croûtons, parmesan",   20000, "ENTREE")
        p4  = plat(r1, "Jus de Bissap",       "Jus d'hibiscus frais sucré",            8000, "BOISSON")
        p5  = plat(r1, "Beignets de banane",  "Beignets maison, banane plantain",     15000, "DESSERT")
        p6  = plat(r1, "Riz blanc",           "Riz vapeur nature",                     5000, "ACCOMPAGNEMENT")
        _   = plat(r1, "Soupe de Légumes",    "Soupe du marché — indisponible",       18000, "ENTREE",         dispo=False)
        p8  = plat(r1, "Eau minérale",        "50 cl",                                 5000, "BOISSON")
        p9  = plat(r1, "Thiébou Djeun Blanc", "Riz au poisson blanc",                 42000, "PLAT",           cuisine=True)
        p10 = plat(r1, "Jus Gingembre",       "Jus de gingembre maison",               7000, "BOISSON")

        # Plats Chez Mariama
        plat(r2, "Mafé Bœuf",   "Ragoût de bœuf à la pâte d'arachide", 50000, "PLAT", cuisine=True)
        plat(r2, "Ginger frais","Jus de gingembre maison",               7000, "BOISSON")

        # ── Tables ────────────────────────────────────────────────────────────
        for num, places, usr in [("T01",4,u_t1),("T02",2,u_t2),("T03",6,u_t3),("T04",4,u_t4)]:
            TableRestaurant.objects.create(
                restaurant=r1, numero_table=num, nombre_places=places, utilisateur=usr
            )

        # ── Caisses générales ─────────────────────────────────────────────────
        CaisseGenerale.objects.create(restaurant=r1, solde=Decimal("1800000"), solde_initial=Decimal("500000"))
        CaisseGenerale.objects.create(restaurant=r2, solde=Decimal("800000"),  solde_initial=Decimal("300000"))

        # ── CaisseGlobale — 6 jours fermés + aujourd'hui ouverte ─────────────
        past_caisses = {}   # day_offset -> CaisseGlobale
        for i in range(6, 0, -1):
            day = today - timedelta(days=i)
            cg = CaisseGlobale.objects.create(
                restaurant=r1,
                date_ouverture=day,
                solde=Decimal("0"),
                is_closed=True,
                closed_at=self._dt(day, 23),
                fermee_par=u_cpt,
                montant_physique_fermeture=Decimal("0"),
            )
            past_caisses[-i] = cg

        cg_today = CaisseGlobale.objects.create(
            restaurant=r1,
            date_ouverture=today,
            solde=Decimal("0"),
            is_closed=False,
        )
        past_caisses[0] = cg_today

        # ── CaisseComptable — ouverte aujourd'hui ─────────────────────────────
        cc = CaisseComptable.objects.create(
            restaurant=r1,
            comptable=u_cpt,
            solde=Decimal("500000"),
            is_closed=False,
        )
        # Approvisionnement d'ouverture
        MouvementCaisse.objects.create(
            caisse_comptable=cc,
            type_mouvement="approvisionnement",
            montant=Decimal("500000"),
            motif="Approvisionnement journalier depuis caisse générale",
            effectue_par=u_cpt,
        )

        # ── Scénarios de commandes ────────────────────────────────────────────
        # (day_offset, heure, minute, table_user, [(plat, qty)], serveur, cuisinier, statut)
        SCENARIOS = [
            # ── J-6
            (-6, 12, 30, u_t1, [(p1,1),(p4,1)],         u_serveur, u_cuis, "payee"),
            (-6, 13,  0, u_t2, [(p2,1),(p8,1)],         u_serveur, u_cuis, "payee"),
            (-6, 19, 30, u_t3, [(p3,1),(p6,1)],         u_serveur, None,   "payee"),
            (-6, 20,  0, u_t4, [(p2,1),(p5,1),(p4,2)],  u_serveur, u_cuis, "payee"),
            # ── J-5
            (-5, 12, 45, u_t1, [(p1,1),(p6,1),(p8,2)],  u_serveur, u_cuis, "payee"),
            (-5, 13, 15, u_t2, [(p3,1),(p2,1),(p4,1)],  u_serveur, u_cuis, "payee"),
            (-5, 20, 30, u_t3, [(p2,2),(p8,1)],         u_serveur, u_cuis, "payee"),
            # ── J-4
            (-4, 12,  0, u_t1, [(p1,1),(p4,1)],         u_serveur, u_cuis, "payee"),
            (-4, 13, 30, u_t4, [(p2,1),(p6,1)],         u_serveur, u_cuis, "payee"),
            (-4, 19,  0, u_t2, [(p3,1),(p5,1),(p4,1)],  u_serveur, None,   "payee"),
            (-4, 20,  0, u_t3, [(p1,1),(p8,1),(p5,1)],  u_serveur, u_cuis, "payee"),
            # ── J-3
            (-3, 12,  0, u_t1, [(p2,1),(p4,2)],         u_serveur, u_cuis, "payee"),
            (-3, 13, 30, u_t2, [(p1,1),(p6,1)],         u_serveur, u_cuis, "payee"),
            (-3, 20,  0, u_t4, [(p3,1),(p2,1),(p8,1)],  u_serveur, u_cuis, "payee"),
            # ── J-2
            (-2, 12, 30, u_t1, [(p1,1),(p4,1),(p5,1)],  u_serveur, u_cuis, "payee"),
            (-2, 13,  0, u_t2, [(p2,1),(p6,2)],         u_serveur, u_cuis, "payee"),
            (-2, 19, 30, u_t3, [(p3,1),(p4,2)],         u_serveur, None,   "payee"),
            (-2, 20, 30, u_t4, [(p1,1),(p8,1),(p4,1)],  u_serveur, u_cuis, "payee"),
            # ── J-1
            (-1, 12,  0, u_t1, [(p9,1),(p6,1),(p4,1)],  u_serveur, u_cuis, "payee"),
            (-1, 12, 30, u_t2, [(p2,1),(p5,1),(p8,1)],  u_serveur, u_cuis, "payee"),
            (-1, 13,  0, u_t3, [(p3,2),(p6,1)],         u_serveur, None,   "payee"),
            (-1, 19,  0, u_t4, [(p1,1),(p4,2),(p5,1)],  u_serveur, u_cuis, "payee"),
            (-1, 20,  0, u_t1, [(p2,1),(p10,1)],        u_serveur, u_cuis, "payee"),
            # ── Aujourd'hui
            (0,  12,  0, u_t1, [(p1,1),(p4,1)],         None,      None,   "en_attente"),
            (0,  12, 30, u_t2, [(p2,1),(p6,1),(p8,1)],  None,      u_cuis, "prete"),
            (0,  13,  0, u_t3, [(p3,1),(p5,1)],         u_serveur, None,   "payee"),
        ]

        day_revenue = {i: Decimal("0") for i in range(-6, 1)}

        for day_off, h, m, tbl, items, serv, cuis, statut in SCENARIOS:
            day = today + timedelta(days=day_off)
            when = self._dt(day, h, m)
            montant = sum(p.prix_unitaire * q for p, q in items)

            cmd = Commande.objects.create(
                restaurant=r1,
                table=tbl,
                montant_total=montant,
                statut=statut,
                serveur_ayant_servi=serv if statut in ("servie", "payee") else None,
                cuisinier_ayant_prepare=cuis if statut in ("prete", "servie", "payee") else None,
                date_paiement=when if statut == "payee" else None,
            )
            # Bypass auto_now_add pour date_commande
            Commande.objects.filter(pk=cmd.pk).update(date_commande=when)

            for plat_obj, qty in items:
                CommandeItem.objects.create(
                    commande=cmd,
                    plat=plat_obj,
                    quantite=qty,
                    prix_unitaire=plat_obj.prix_unitaire,
                )

            if statut == "payee":
                paiement = Paiement.objects.create(commande=cmd, montant=montant)
                Paiement.objects.filter(pk=paiement.pk).update(date_paiement=when)

                cg = past_caisses.get(day_off)
                if cg:
                    remise = RemiseServeur.objects.create(
                        caisse_globale=cg,
                        paiement=paiement,
                        montant_virtuel=montant,
                        montant_physique=montant,
                        valide=day_off < 0,
                        validee_par=u_cpt if day_off < 0 else None,
                        serveur=serv if serv else u_serveur,
                    )
                    RemiseServeur.objects.filter(pk=remise.pk).update(
                        created_at=when, updated_at=when
                    )
                    day_revenue[day_off] += montant

        # Mise à jour des soldes des caisses globales fermées
        for day_off, cg in past_caisses.items():
            if day_off < 0:
                rev = day_revenue[day_off]
                CaisseGlobale.objects.filter(pk=cg.pk).update(
                    solde=rev, montant_physique_fermeture=rev
                )
            else:
                CaisseGlobale.objects.filter(pk=cg.pk).update(
                    solde=day_revenue[0]
                )

        # ── Dépenses ─────────────────────────────────────────────────────────
        depenses = [
            (-2, "Achat légumes frais — marché Madina",   Decimal("45000")),
            (-1, "Achat produits d'entretien",             Decimal("25000")),
            (-1, "Eau en bouteille — 12 packs",            Decimal("30000")),
            (0,  "Emballages et sachets kraft",            Decimal("20000")),
        ]
        for day_off, motif, montant in depenses:
            day = today + timedelta(days=day_off)
            dep = Depense.objects.create(
                caisse_comptable=cc,
                motif=motif,
                montant=montant,
                date_depense=day,
                enregistree_par=u_cpt,
            )
            Depense.objects.filter(pk=dep.pk).update(
                date_enregistrement=self._dt(day, 9, 30)
            )
            mv = MouvementCaisse.objects.create(
                caisse_comptable=cc,
                type_mouvement="depense",
                montant=montant,
                motif=motif,
                effectue_par=u_cpt,
            )
            MouvementCaisse.objects.filter(pk=mv.pk).update(
                created_at=self._dt(day, 9, 30)
            )
