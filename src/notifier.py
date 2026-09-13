"""Envoi des notifications lorsqu'une nouvelle annonce correspond a une recherche."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import requests

from .vinted_client import VintedItem

logger = logging.getLogger("vinted_watcher.notifier")

_COULEUR_EMBED = 0x09B1BA  # bleu-vert Vinted


def mask_webhook_url(url: str | None) -> str:
    """Tronque une URL de webhook pour affichage (jamais le webhook complet en clair)."""
    if not url:
        return "(webhook global)"
    marqueur = "/webhooks/"
    if marqueur in url:
        prefixe, _, reste = url.partition(marqueur)
        identifiant = reste.split("/")[0]
        return f"{prefixe}{marqueur}{identifiant[:4]}.../***"
    return url[:20] + "..."


class Notifier(ABC):
    @abstractmethod
    def notify(self, item: VintedItem, search_nom: str) -> bool:
        """Notifie qu'une nouvelle annonce correspond a la recherche donnee.

        Renvoie True en cas de succes, False sinon (l'appelant du scheduler
        ignore la valeur de retour, mais elle sert a l'interface web pour
        afficher le resultat d'un test de webhook).
        """


_MAX_PHOTOS_GALERIE = 4  # 1 embed principal + jusqu'a 3 embeds photo supplementaires


class DiscordNotifier(Notifier):
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def notify(self, item: VintedItem, search_nom: str) -> bool:
        fields = [
            {"name": "Prix demande", "value": f"{item.price:.2f} {item.currency}", "inline": True},
        ]
        # total_item_price (prix + protection acheteur) n'est affiche que si l'API
        # l'a bien fourni pour cette annonce : jamais de calcul approximatif invente.
        if item.total_price is not None:
            fields.append(
                {
                    "name": "Prix total (protection acheteur)",
                    "value": f"{item.total_price:.2f} {item.total_currency or item.currency}",
                    "inline": True,
                }
            )
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
        photos = item.photos or ([item.photo_url] if item.photo_url else [])
        if photos:
            embed["image"] = {"url": photos[0]}

        # Plusieurs embeds partageant le meme `url` sont regroupes par Discord en une
        # galerie d'images cliquable dans un seul message.
        embeds = [embed]
        for photo_url in photos[1:_MAX_PHOTOS_GALERIE]:
            embeds.append({"url": item.url, "image": {"url": photo_url}})

        payload: dict = {"embeds": embeds}

        webhook_url = self.webhook_url
        if item.url:
            payload["components"] = [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 5,
                            "label": "Voir l'annonce sur Vinted",
                            "url": item.url,
                        }
                    ],
                }
            ]
            separateur = "&" if "?" in webhook_url else "?"
            webhook_url = f"{webhook_url}{separateur}with_components=true"

        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            logger.error("Echec de l'envoi de la notification Discord pour '%s' : %s", item.title, exc)
            return False


class WebNotifier(Notifier):
    """TODO (V2) : notifier branche sur un futur dashboard web.

    Squelette volontairement non implemente : permettra d'ajouter un dashboard
    (ex: websocket, base partagee) sans modifier le reste du code (scheduler,
    vinted_client, storage restent inchanges).
    """

    def __init__(self) -> None:
        raise NotImplementedError("WebNotifier sera implemente en V2.")

    def notify(self, item: VintedItem, search_nom: str) -> bool:
        raise NotImplementedError
