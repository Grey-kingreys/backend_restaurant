"""
Crée (ou réactive) le super administrateur plateforme à partir de variables
d'environnement. Idempotent — conçu pour tourner à chaque déploiement.

Sert à débloquer l'accès en production quand le seed de démo est désactivé
(RUN_SEED=false) : sans lui, aucun compte Rsuper_admin n'existe et le site est
inaccessible.

Variables d'environnement :
  SUPERADMIN_PASSWORD   (obligatoire) — sans elle, la commande ne fait rien
  SUPERADMIN_LOGIN      (défaut: "superadmin")
  SUPERADMIN_EMAIL      (optionnel)
  SUPERADMIN_NOM        (défaut: "Administrateur Plateforme")
  SUPERADMIN_RESET_PASSWORD  ("true" pour forcer la réinitialisation du mot de
                              passe d'un compte déjà existant ; défaut: non)
"""
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User

try:
    from apps.accounts.models import RoleConfig
except ImportError:  # RoleConfig absent sur d'anciennes versions du modèle
    RoleConfig = None


def _env(name, default=""):
    return (os.getenv(name) or default).strip()


class Command(BaseCommand):
    help = "Crée/réactive le super administrateur plateforme depuis les variables d'environnement (idempotent)."

    def handle(self, *args, **options):
        password = _env("SUPERADMIN_PASSWORD")
        if not password:
            self.stdout.write(self.style.WARNING(
                "SUPERADMIN_PASSWORD non défini — création du super admin ignorée."
            ))
            return

        login = _env("SUPERADMIN_LOGIN", "superadmin")
        email = _env("SUPERADMIN_EMAIL") or None
        nom = _env("SUPERADMIN_NOM", "Administrateur Plateforme")
        reset_password = _env("SUPERADMIN_RESET_PASSWORD").lower() == "true"

        role_config = None
        if RoleConfig is not None:
            role_config = RoleConfig.objects.filter(
                slug="Rsuper_admin", is_system=True
            ).first()

        with transaction.atomic():
            user = User.objects.filter(login=login).first()
            created = user is None
            if created:
                user = User(login=login)

            # Attributs structurels garantis à chaque exécution (réactive un compte
            # éventuellement désactivé, sans écraser le nom/email déjà personnalisés).
            user.role = "Rsuper_admin"
            user.restaurant = None
            user.is_staff = True
            user.is_superuser = True
            user.actif = True
            user.is_active = True
            user.must_change_password = False
            if role_config is not None:
                user.role_config = role_config
            if created:
                user.nom_complet = nom
                if email:
                    user.email = email
            elif email:
                user.email = email

            # Mot de passe : défini à la création ; sur un compte existant, on ne le
            # touche que si SUPERADMIN_RESET_PASSWORD=true (pour ne pas écraser un
            # mot de passe changé par l'admin via l'interface).
            if created or reset_password:
                user.set_password(password)

            user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f"Super admin '{login}' créé."))
        elif reset_password:
            self.stdout.write(self.style.SUCCESS(
                f"Super admin '{login}' déjà présent — réactivé, mot de passe réinitialisé."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Super admin '{login}' déjà présent — réactivé (mot de passe inchangé)."
            ))
