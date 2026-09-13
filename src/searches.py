"""Chargement, validation et gestion des recherches definies par l'utilisateur (config/searches.json)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger("vinted_watcher.searches")

DEFAULT_SEARCHES_PATH = "config/searches.json"
MIN_INTERVALLE_MINUTES = 1


@dataclass
class Search:
    id: str
    nom: str
    mots_cles: str
    prix_min: float | None = None
    prix_max: float | None = None
    devise: str = "EUR"
    actif: bool = True
    intervalle_minutes: int = 3
    catalog_ids: str | None = None
    etat_ids: str | None = None

    def __post_init__(self) -> None:
        # Garde-fou : ne jamais verifier une recherche plus souvent qu'une fois par minute.
        if self.intervalle_minutes < MIN_INTERVALLE_MINUTES:
            logger.warning(
                "Intervalle trop court pour '%s' (%s min), force a %s min.",
                self.id,
                self.intervalle_minutes,
                MIN_INTERVALLE_MINUTES,
            )
            self.intervalle_minutes = MIN_INTERVALLE_MINUTES


def load_searches(path: str = DEFAULT_SEARCHES_PATH) -> list[Search]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    with file_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return [Search(**item) for item in raw]


def save_searches(searches: list[Search], path: str = DEFAULT_SEARCHES_PATH) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as f:
        json.dump([asdict(s) for s in searches], f, ensure_ascii=False, indent=2)


def _slugify(nom: str) -> str:
    slug = "".join(c.lower() if c.isalnum() else "-" for c in nom)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def add_search(
    nom: str,
    mots_cles: str,
    prix_min: float | None = None,
    prix_max: float | None = None,
    devise: str = "EUR",
    intervalle_minutes: int = 3,
    catalog_ids: str | None = None,
    etat_ids: str | None = None,
    path: str = DEFAULT_SEARCHES_PATH,
) -> Search:
    searches = load_searches(path)
    search_id = _slugify(nom)
    if any(s.id == search_id for s in searches):
        raise ValueError(f"Une recherche avec l'id '{search_id}' existe deja.")

    search = Search(
        id=search_id,
        nom=nom,
        mots_cles=mots_cles,
        prix_min=prix_min,
        prix_max=prix_max,
        devise=devise,
        intervalle_minutes=intervalle_minutes,
        catalog_ids=catalog_ids,
        etat_ids=etat_ids,
    )
    searches.append(search)
    save_searches(searches, path)
    return search


def set_active(search_id: str, actif: bool, path: str = DEFAULT_SEARCHES_PATH) -> None:
    searches = load_searches(path)
    for s in searches:
        if s.id == search_id:
            s.actif = actif
            save_searches(searches, path)
            return
    raise ValueError(f"Recherche '{search_id}' introuvable.")


def remove_search(search_id: str, path: str = DEFAULT_SEARCHES_PATH) -> None:
    searches = load_searches(path)
    remaining = [s for s in searches if s.id != search_id]
    if len(remaining) == len(searches):
        raise ValueError(f"Recherche '{search_id}' introuvable.")
    save_searches(remaining, path)
