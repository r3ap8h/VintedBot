"""Envoi des notifications lorsqu'une nouvelle annonce correspond a une recherche."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import requests

from .vinted_client import VintedItem

logger = logging.getLogger("vinted_watcher.notifier")

_COULEUR_EMBED = 0x09B1BA  # bleu-vert Vinted


class Notifier(ABC):
    @abstractmethod
    def notify(self, item: VintedItem, search_nom: str) -> None:
        """Notifie qu'une nouvelle annonce correspond a la recherche donnee."""


class DiscordNotifier(Notifier):
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def notify(self, item: VintedItem, search_nom: str) -> None:
        fields = []
        if item.brand:
            fields.append({"name": "Marque", "value": item.brand, "inline": True})
        if item.size:
            fields.append({"name": "Taille", "value": item.size, "inline": True})
        if item.status:
            fields.append({"name": "Etat", "value": item.status, "inline": True})

        embed = {
            "title": item.title,
            "url": item.url,
            "description": f"**{item.price:.2f} {item.currency}**",
            "color": _COULEUR_EMBED,
            "fields": fields,
            "footer": {"text": f"Recherche : {search_nom}"},
        }
        if item.photo_url:
            embed["thumbnail"] = {"url": item.photo_url}

        payload = {"embeds": [embed]}

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Echec de l'envoi de la notification Discord pour '%s' : %s", item.title, exc)


class WebNotifier(Notifier):
    """TODO (V2) : notifier branche sur un futur dashboard web.

    Squelette volontairement non implemente : permettra d'ajouter un dashboard
    (ex: websocket, base partagee) sans modifier le reste du code (scheduler,
    vinted_client, storage restent inchanges).
    """

    def __init__(self) -> None:
        raise NotImplementedError("WebNotifier sera implemente en V2.")

    def notify(self, item: VintedItem, search_nom: str) -> None:
        raise NotImplementedError
