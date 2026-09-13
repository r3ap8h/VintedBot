"""Boucle principale de planification : verifie chaque recherche a intervalle regulier.

Utilise un tas (min-heap) de "prochaine verification" plutot qu'un scheduler a
dependance externe (APScheduler) : plus simple, plus leger, et le comportement
attendu (jitter, decalage entre recherches, jamais moins d'une minute) est
explicite et facile a auditer.
"""

from __future__ import annotations

import heapq
import logging
import random
import time

from .notifier import Notifier
from .searches import Search
from .storage import is_new, is_search_known, mark_seen
from .vinted_client import RateLimitError, VintedClient, VintedClientError

logger = logging.getLogger("vinted_watcher.scheduler")

JITTER_SECONDS = 30


def check_search(client: VintedClient, search: Search, notifier: Notifier) -> None:
    """Verifie une recherche : detecte les nouveautes et notifie.

    N'importe quelle erreur liee a l'API Vinted est capturee ici (sauf
    RateLimitError, propagee pour que l'appelant adapte le delai avant la
    prochaine tentative) afin qu'une recherche en echec n'affecte jamais les
    autres.
    """
    try:
        items = client.search(
            mots_cles=search.mots_cles,
            prix_min=search.prix_min,
            prix_max=search.prix_max,
            devise=search.devise,
            catalog_ids=search.catalog_ids,
            etat_ids=search.etat_ids,
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

    nouveautes = [item for item in items if is_new(search.id, item.id)]
    if nouveautes:
        logger.info("%d nouvelle(s) annonce(s) pour '%s'.", len(nouveautes), search.nom)
    for item in nouveautes:
        notifier.notify(item, search.nom)
        mark_seen(search.id, item)


def run_forever(searches: list[Search], notifier: Notifier) -> None:
    active = [s for s in searches if s.actif]
    if not active:
        logger.warning("Aucune recherche active, rien a surveiller.")
        return

    client = VintedClient()
    by_id = {s.id: s for s in active}
    heap: list[tuple[float, str]] = []

    now = time.monotonic()
    for i, search in enumerate(active):
        # Decale le premier passage de chaque recherche pour ne pas toutes les
        # interroger en meme temps.
        offset = (i * 5) + random.uniform(0, JITTER_SECONDS)
        heapq.heappush(heap, (now + offset, search.id))

    logger.info("Surveillance demarree pour %d recherche(s).", len(active))
    try:
        while True:
            next_ts, search_id = heap[0]
            wait = next_ts - time.monotonic()
            if wait > 0:
                time.sleep(min(wait, 5))
                continue

            heapq.heappop(heap)
            search = by_id[search_id]
            try:
                check_search(client, search, notifier)
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
