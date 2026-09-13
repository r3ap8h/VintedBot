"""Extraction des criteres de recherche a partir d'une URL Vinted copiee depuis le site.

Vinted n'a pas de table stable "nom de filtre -> id" (catalogues, marques, tailles,
couleurs, matieres... representent des milliers d'ids, sans mapping documente).
La solution robuste consiste a laisser l'utilisateur construire sa recherche avec
l'interface web normale de vinted.fr, puis a parser l'URL resultante : elle
contient deja tous les filtres choisis sous forme de parametres de requete.

Verifie en conditions reelles (navigateur) : le frontend utilise `catalog[]` pour
la categorie alors que l'API interne attend `catalog_ids` — c'est la seule
divergence de nommage observee, les autres filtres (`brand_ids[]`, `status_ids[]`,
`size_ids[]`, `color_ids[]`, `material_ids[]`, ...) portent deja le meme nom cote
front (juste suffixe par `[]`) et cote API.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("vinted_watcher.url_parser")

# Parametres dont le nom differe entre l'URL du site (frontend) et l'API interne.
_RENAME_MAP = {
    "catalog": "catalog_ids",
}

# Parametres purement lies a l'affichage/au tracking, sans equivalent utile pour l'API.
_IGNORED_PARAMS = {"page", "time", "search_id", "order"}


@dataclass
class ParsedVintedUrl:
    mots_cles: str
    prix_min: float | None
    prix_max: float | None
    devise: str
    filtres_bruts: dict[str, list[str]] = field(default_factory=dict)


def parse_vinted_search_url(url: str) -> ParsedVintedUrl:
    """Extrait mots-cles, prix et filtres bruts depuis une URL de recherche/catalogue Vinted."""
    candidate = url if "://" in url else f"https://{url}"
    parsed = urlparse(candidate)
    if not parsed.scheme.startswith("http") or not parsed.netloc:
        raise ValueError(f"URL invalide : {url!r}")

    query = parse_qs(parsed.query, keep_blank_values=False)

    mots_cles = ""
    prix_min: float | None = None
    prix_max: float | None = None
    devise = "EUR"
    filtres_bruts: dict[str, list[str]] = {}

    for raw_key, raw_values in query.items():
        key = raw_key[:-2] if raw_key.endswith("[]") else raw_key

        # Normalise a la fois le format "repete" (status_ids[]=2&status_ids[]=3)
        # et le format "virgule" (status_ids=2,3) vers une simple liste de valeurs.
        values: list[str] = []
        for raw_value in raw_values:
            values.extend(part for part in raw_value.split(",") if part)

        if key == "search_text":
            mots_cles = values[0] if values else mots_cles
        elif key == "price_from":
            prix_min = float(values[0]) if values else None
        elif key == "price_to":
            prix_max = float(values[0]) if values else None
        elif key == "currency":
            devise = values[0] if values else devise
        elif key in _IGNORED_PARAMS:
            continue
        else:
            api_key = _RENAME_MAP.get(key, key)
            existing = filtres_bruts.setdefault(api_key, [])
            for value in values:
                if value not in existing:
                    existing.append(value)

    if not mots_cles and not filtres_bruts:
        logger.warning(
            "Aucun mot-cle ni filtre reconnu dans l'URL fournie : verifie qu'il "
            "s'agit bien d'une URL de recherche/catalogue Vinted."
        )

    return ParsedVintedUrl(
        mots_cles=mots_cles,
        prix_min=prix_min,
        prix_max=prix_max,
        devise=devise,
        filtres_bruts=filtres_bruts,
    )
