"""Chargement, validation et gestion des recherches definies par l'utilisateur (config/searches.json)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from .url_parser import parse_vinted_search_url

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
    filtres_bruts: dict[str, list[str]] = field(default_factory=dict)
    webhook_url: str | None = None

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


def summarize_filtres(filtres: dict[str, list[str]]) -> str:
    """Resume lisible des filtres avances, ex: 'catalog_ids=1238, status_ids=2,3'."""
    if not filtres:
        return ""
    return ", ".join(f"{cle}={','.join(valeurs)}" for cle, valeurs in filtres.items())


def _migrate_raw(raw: dict) -> tuple[dict, bool]:
    """Adapte une entree JSON a l'ancien format (catalog_ids/etat_ids scalaires) au format actuel.

    Renvoie (raw_migre, a_change) pour savoir s'il faut re-ecrire le fichier.
    """
    raw = dict(raw)
    a_change = False

    filtres = raw.pop("filtres_bruts", None)
    if filtres is None:
        filtres = {}
        a_change = True

    old_catalog = raw.pop("catalog_ids", None)
    if old_catalog:
        valeurs = old_catalog if isinstance(old_catalog, list) else [old_catalog]
        filtres.setdefault("catalog_ids", [str(v) for v in valeurs])
        a_change = True

    old_etat = raw.pop("etat_ids", None)
    if old_etat:
        valeurs = old_etat if isinstance(old_etat, list) else [old_etat]
        filtres.setdefault("status_ids", [str(v) for v in valeurs])
        a_change = True

    raw["filtres_bruts"] = filtres

    if "webhook_url" not in raw:
        raw["webhook_url"] = None
        a_change = True

    return raw, a_change


def load_searches(path: str = DEFAULT_SEARCHES_PATH) -> list[Search]:
    file_path = Path(path)
    if not file_path.exists():
        return []

    with file_path.open("r", encoding="utf-8") as f:
        raw_list = json.load(f)

    searches: list[Search] = []
    besoin_migration = False
    for raw in raw_list:
        raw_migre, a_change = _migrate_raw(raw)
        besoin_migration = besoin_migration or a_change
        searches.append(Search(**raw_migre))

    if besoin_migration:
        logger.info("Migration du format de config/searches.json (filtres_bruts/webhook_url).")
        save_searches(searches, path)

    return searches


def save_searches(searches: list[Search], path: str = DEFAULT_SEARCHES_PATH) -> None:
    """Ecriture atomique : fichier temporaire puis remplacement, pour eviter toute

    corruption si le scheduler relit le fichier au meme moment.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=file_path.parent, prefix=".searches-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump([asdict(s) for s in searches], f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, file_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def get_search(search_id: str, path: str = DEFAULT_SEARCHES_PATH) -> Search | None:
    for s in load_searches(path):
        if s.id == search_id:
            return s
    return None


def _slugify(nom: str) -> str:
    slug = "".join(c.lower() if c.isalnum() else "-" for c in nom)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _generate_id(nom: str, searches: list[Search]) -> str:
    base = _slugify(nom) or "recherche"
    search_id = base
    suffixe = 2
    ids_existants = {s.id for s in searches}
    while search_id in ids_existants:
        search_id = f"{base}-{suffixe}"
        suffixe += 1
    return search_id


def add_search(
    nom: str,
    mots_cles: str,
    prix_min: float | None = None,
    prix_max: float | None = None,
    devise: str = "EUR",
    intervalle_minutes: int = 3,
    webhook_url: str | None = None,
    path: str = DEFAULT_SEARCHES_PATH,
) -> Search:
    """Cree une recherche simple (mots-cles + prix), sans filtres avances."""
    searches = load_searches(path)
    search = Search(
        id=_generate_id(nom, searches),
        nom=nom,
        mots_cles=mots_cles,
        prix_min=prix_min,
        prix_max=prix_max,
        devise=devise,
        intervalle_minutes=intervalle_minutes,
        webhook_url=webhook_url or None,
    )
    searches.append(search)
    save_searches(searches, path)
    return search


def add_search_from_url(
    nom: str,
    url: str,
    intervalle_minutes: int = 3,
    webhook_url: str | None = None,
    path: str = DEFAULT_SEARCHES_PATH,
) -> Search:
    """Cree une recherche a partir d'une URL de recherche/catalogue copiee sur vinted.fr."""
    parsed = parse_vinted_search_url(url)
    searches = load_searches(path)
    search = Search(
        id=_generate_id(nom, searches),
        nom=nom,
        mots_cles=parsed.mots_cles,
        prix_min=parsed.prix_min,
        prix_max=parsed.prix_max,
        devise=parsed.devise,
        intervalle_minutes=intervalle_minutes,
        filtres_bruts=parsed.filtres_bruts,
        webhook_url=webhook_url or None,
    )
    searches.append(search)
    save_searches(searches, path)
    return search


def update_search(search_id: str, path: str = DEFAULT_SEARCHES_PATH, **changes) -> Search:
    searches = load_searches(path)
    for i, s in enumerate(searches):
        if s.id == search_id:
            updated = replace(s, **changes)
            searches[i] = updated
            save_searches(searches, path)
            return updated
    raise ValueError(f"Recherche '{search_id}' introuvable.")


def set_active(search_id: str, actif: bool, path: str = DEFAULT_SEARCHES_PATH) -> None:
    update_search(search_id, path=path, actif=actif)


def remove_search(search_id: str, path: str = DEFAULT_SEARCHES_PATH) -> None:
    searches = load_searches(path)
    remaining = [s for s in searches if s.id != search_id]
    if len(remaining) == len(searches):
        raise ValueError(f"Recherche '{search_id}' introuvable.")
    save_searches(remaining, path)
