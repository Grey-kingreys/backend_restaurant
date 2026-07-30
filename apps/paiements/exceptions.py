"""Exceptions métier de l'app paiements."""


class ErreurMetier(ValueError):
    """Erreur métier dont le message est volontairement destiné à l'utilisateur final.

    Sous-classe `ValueError` pour rester rétro-compatible avec les `except ValueError`
    et `pytest.raises(ValueError)` existants. À utiliser quand on veut qu'un message
    précis (« solde insuffisant », « demande déjà traitée »…) remonte jusqu'au client.

    Les vues ne renvoient `str(e)` au client QUE pour ce type dédié ; tout autre
    `ValueError` inattendu reçoit un message générique (pas de fuite d'info interne).
    """
