"""Filtrage cote application sur les champs texte lisibles renvoyes par l'API Vinted.

Vinted n'expose pas de table stable "nom de filtre -> id" pour l'etat, la marque,
la taille... (non documente, changeant sans preavis). L'API de recherche renvoie
en revanche, pour chaque annonce, des champs texte directement lisibles
(`brand_title`, `size_title`, `status`) : on compare ces champs aux criteres
definis sur la recherche, sans jamais avoir besoin d'un id interne.

Verifie en conditions reelles (voir vinted_client.py) : la couleur, la matiere et
le motif ne sont disponibles ni dans la reponse de recherche, ni dans le detail
d'une annonce (l'endpoint `/api/v2/items/{id}` renvoie 404 avec une session
anonyme) - ces criteres ne sont donc pas geres ici.
"""

from __future__ import annotations

import unicodedata

from .searches import SANS_MARQUE, Search
from .vinted_client import VintedItem


def _normalize(texte: str | None) -> str:
    if not texte:
        return ""
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")
    return sans_accents.strip().lower()


def _contient(valeur: str | None, recherche: str) -> bool:
    return _normalize(recherche) in _normalize(valeur)


def correspond(item: VintedItem, search: Search) -> bool:
    """Verifie qu'une annonce correspond a tous les criteres texte definis sur la recherche.

    Un critere vide/None sur la recherche ne filtre rien (compatible avec les
    recherches existantes qui ne definissent aucun de ces criteres).
    """
    if search.terme_obligatoire and not _contient(item.title, search.terme_obligatoire):
        return False

    if search.etats:
        etats_voulus = {_normalize(e) for e in search.etats}
        if _normalize(item.status) not in etats_voulus:
            return False

    if search.marque:
        if _normalize(search.marque) == _normalize(SANS_MARQUE):
            if item.brand:
                return False
        elif not _contient(item.brand, search.marque):
            return False

    if search.taille and not _contient(item.size, search.taille):
        return False

    return True
