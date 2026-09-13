"""Boucle principale de planification : verifie chaque recherche a intervalle regulier.

Utilise un tas (min-heap) de "prochaine verification" plutot qu'un scheduler a
dependance externe (APScheduler) : plus simple, plus leger, et le comportement
attendu (jitter, decalage entre recherches, jamais moins d'une minute) est
explicite et facile a auditer.

La config/searches.json est rechargee periodiquement pour prendre en compte les
modifications faites depuis l'interface web (ou la CLI) sans redemarrer le process.
"""

from __future__ import annotations

import heapq
import logging
import random
import time

from .filtres_texte import correspond
from .notifier import DiscordNotifier, Notifier
from .searches import DEFAULT_SEARCHES_PATH, Search, build_search_text, load_searches
from .storage import is_new, is_search_known, mark_seen
from .vinted_client import RateLimitError, VintedClient, VintedClientError

logger = logging.getLogger("vinted_watcher.scheduler")

JITTER_SECONDS = 30
RELOAD_INTERVAL_SECONDS = 90


def _resolve_notifier(
    search: Search, default_webhook_url: str, notifier_cache: dict[str, Notifier]
) -> Notifier:
    """Choisit le notifier a utiliser pour une recherche, avec un petit cache par webhook."""
    webhook_url = default_webhook_url
    if search.webhook_url:
        if search.webhook_url.strip().startswith("http"):
            webhook_url = search.webhook_url.strip()
        else:
            logger.warning(
                "webhook_url invalide pour '%s' ('%s'), utilisation du webhook global.",
                search.nom,
                search.webhook_url,
            )

    if webhook_url not in notifier_cache:
        notifier_cache[webhook_url] = DiscordNotifier(webhook_url)
    return notifier_cache[webhook_url]


def check_search(
    client: VintedClient,
    search: Search,
    default_webhook_url: str,
    notifier_cache: dict[str, Notifier],
) -> None:
    """Verifie une recherche : detecte les nouveautes et notifie.

    N'importe quelle erreur liee a l'API Vinted est capturee ici (sauf
    RateLimitError, propagee pour que l'appelant adapte le delai avant la
    prochaine tentative) afin qu'une recherche en echec n'affecte jamais les
    autres.
    """
    try:
        items = client.search(
            mots_cles=build_search_text(search),
            prix_min=search.prix_min,
            prix_max=search.prix_max,
            devise=search.devise,
            filtres_bruts=search.filtres_bruts,
        )
    except RateLimitError:
        raise
    except VintedClientError as exc:
        logger.error("Erreur lors de la verification de '%s' : %s", search.nom, exc)
        return

    premiere_fois = not is_search_known(search.id)
    if premiere_fois:
        logger.info(
            "Premiere verification de '%s' : %d annonce(s) enregistree(s) sans notification.",
            search.nom,
            len(items),
        )
        for item in items:
            mark_seen(search.id, item)
        return

    # Toutes les annonces nouvellement recues sont marquees vues (pour ne pas les
    # ré-analyser au prochain passage), mais seules celles qui passent les criteres
    # texte de la recherche (etat, marque, taille...) declenchent une notification.
    nouveautes = [item for item in items if is_new(search.id, item.id)]
    if nouveautes:
        a_notifier = [item for item in nouveautes if correspond(item, search)]
        if a_notifier:
            logger.info("%d nouvelle(s) annonce(s) pour '%s'.", len(a_notifier), search.nom)
            notifier = _resolve_notifier(search, default_webhook_url, notifier_cache)
            for item in a_notifier:
                notifier.notify(item, search.nom)
        for item in nouveautes:
            mark_seen(search.id, item)


def run_forever(default_webhook_url: str, searches_path: str = DEFAULT_SEARCHES_PATH) -> None:
    client = VintedClient()
    notifier_cache: dict[str, Notifier] = {}
    heap: list[tuple[float, str]] = []
    by_id: dict[str, Search] = {}
    scheduled_ids: set[str] = set()

    def _sync_searches() -> None:
        nonlocal by_id
        fresh = {s.id: s for s in load_searches(searches_path) if s.actif}
        now = time.monotonic()
        nouveaux = [sid for sid in fresh if sid not in scheduled_ids]
        for i, sid in enumerate(nouveaux):
            offset = (i * 5) + random.uniform(0, JITTER_SECONDS)
            heapq.heappush(heap, (now + offset, sid))
            scheduled_ids.add(sid)
            logger.info("Nouvelle recherche active detectee : '%s'.", fresh[sid].nom)
        by_id = fresh

    _sync_searches()
    if not by_id:
        logger.warning("Aucune recherche active, rien a surveiller.")
        return

    logger.info("Surveillance demarree pour %d recherche(s).", len(by_id))
    last_reload = time.monotonic()

    try:
        while True:
            if time.monotonic() - last_reload >= RELOAD_INTERVAL_SECONDS:
                _sync_searches()
                last_reload = time.monotonic()

            if not heap:
                time.sleep(1)
                continue

            next_ts, search_id = heap[0]
            wait = next_ts - time.monotonic()
            if wait > 0:
                time.sleep(min(wait, 5))
                continue

            heapq.heappop(heap)
            search = by_id.get(search_id)
            if search is None:
                # Recherche supprimee ou desactivee depuis la derniere synchronisation.
                scheduled_ids.discard(search_id)
                continue

            try:
                check_search(client, search, default_webhook_url, notifier_cache)
                delay = search.intervalle_minutes * 60 + random.uniform(
                    -JITTER_SECONDS, JITTER_SECONDS
                )
            except RateLimitError as exc:
                logger.warning(
                    "Rate limit Vinted sur '%s', prochaine tentative dans %.0fs.",
                    search.nom,
                    exc.retry_after,
                )
                delay = exc.retry_after + random.uniform(0, JITTER_SECONDS)

            delay = max(delay, 60)  # jamais moins d'une minute entre deux verifications
            heapq.heappush(heap, (time.monotonic() + delay, search_id))
    except KeyboardInterrupt:
        logger.info("Arret demande (Ctrl+C), fin de la surveillance.")
