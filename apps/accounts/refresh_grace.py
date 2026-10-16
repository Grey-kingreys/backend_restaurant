"""Période de grâce du rafraîchissement de connexion.

Avec la rotation SimpleJWT, l'ancien refresh est blacklisté dès qu'un nouveau couple
est émis. Si la réponse se perd (réseau faible), le client rejoue l'ancien refresh et
se retrouve déconnecté. On mémorise donc 60 s le couple émis, par `jti` du refresh reçu.

Distinction rotation / déconnexion : seule une rotation crée une entrée de grâce.
Une déconnexion supprime l'entrée du refresh déconnecté (et celle de son parent, voir
`oublier`), donc un refresh blacklisté par logout reste refusé même dans la fenêtre.
"""
from django.core.cache import cache
from rest_framework_simplejwt.state import token_backend

DUREE_GRACE = 60   # secondes
DUREE_VERROU = 10  # secondes, protège l'appel concurrent pendant la rotation


def jti_de(refresh):
    """jti d'un refresh dont la signature et l'expiration sont valides, sinon None.
    La blacklist n'est volontairement pas consultée ici."""
    try:
        return token_backend.decode(refresh, verify=True).get('jti')
    except Exception:
        return None


def _cle_couple(jti):
    return f"refresh_grace:couple:{jti}"


def _cle_parent(jti):
    return f"refresh_grace:parent:{jti}"


def _cle_verrou(jti):
    return f"refresh_grace:verrou:{jti}"


def lire(jti):
    return cache.get(_cle_couple(jti))


def memoriser(jti, couple):
    """Mémorise le couple {access, refresh} émis pour le refresh de jti `jti`."""
    cache.set(_cle_couple(jti), couple, DUREE_GRACE)
    nouveau_jti = jti_de(couple['refresh'])
    if nouveau_jti:
        cache.set(_cle_parent(nouveau_jti), jti, DUREE_GRACE)


def prendre_verrou(jti):
    """True pour un seul appel à la fois par refresh (cache.add est atomique)."""
    return cache.add(_cle_verrou(jti), 1, DUREE_VERROU)


def rendre_verrou(jti):
    cache.delete(_cle_verrou(jti))


def oublier(jti):
    """Déconnexion : supprime la grâce du refresh déconnecté et celle de son parent
    (le parent, rejoué, renverrait sinon le couple dont ce refresh fait partie)."""
    parent = cache.get(_cle_parent(jti))
    cache.delete_many([_cle_couple(jti), _cle_parent(jti)])
    if parent:
        cache.delete(_cle_couple(parent))
