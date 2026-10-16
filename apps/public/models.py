from django.conf import settings
from django.db import models


class CleIdempotence(models.Model):
    """
    Réponse mémorisée d'une requête envoyée avec l'en-tête `Idempotency-Key`
    (commander, réserver). Rejouer la même clé avec le même corps renvoie la
    réponse d'origine sans rien recréer. Purgée après 24 h (tâche Celery).
    """

    cle = models.CharField(max_length=128, verbose_name="Clé d'idempotence")
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='cles_idempotence',
        verbose_name="Utilisateur",
    )
    route = models.CharField(max_length=255, verbose_name="Route")
    empreinte = models.CharField(max_length=64, verbose_name="Empreinte SHA-256 du corps")
    code_reponse = models.PositiveSmallIntegerField(null=True, blank=True)
    corps_reponse = models.JSONField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Clé d'idempotence"
        verbose_name_plural = "Clés d'idempotence"
        constraints = [
            models.UniqueConstraint(
                fields=['cle', 'utilisateur', 'route'],
                nulls_distinct=False,
                name='unique_cle_utilisateur_route',
            ),
        ]

    def __str__(self):
        return f"{self.cle} ({self.route})"
