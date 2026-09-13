"""Client HTTP pour l'API interne (non officielle) de Vinted.

Vinted n'expose aucune API publique documentée. Le site web utilise en interne
l'endpoint `GET /api/v2/catalog/items`, protégé par Datadome (anti-bot). Pour y
accéder, on charge d'abord une page HTML classique de vinted.fr avec un
User-Agent de vrai navigateur afin de récupérer les cookies de session (dont le
cookie Datadome) et un éventuel token CSRF, puis on réutilise cette session pour
les appels à l'API. Cet endpoint n'étant pas documenté officiellement, sa
structure peut changer sans préavis : toutes les erreurs sont donc capturées
proprement (jamais de crash) et remontées sous forme d'exceptions dédiées.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

import requests

logger = logging.getLogger("vinted_watcher.client")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Le token CSRF peut apparaître sous différentes formes dans le HTML selon les
# versions du site : on tente plusieurs motifs, du plus courant au plus rare.
_CSRF_PATTERNS = [
    re.compile(r'<meta[^>]+name="csrf-token"[^>]+content="([^"]+)"'),
    re.compile(r'"CSRF_TOKEN"\s*:\s*"([^"]+)"'),
]


class VintedClientError(Exception):
    """Erreur générique lors d'un appel à l'API Vinted (réseau, 4xx/5xx, JSON invalide...)."""


class RateLimitError(VintedClientError):
    """Levée quand Vinted répond 429 ; contient le délai d'attente conseillé en secondes."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"Rate limit Vinted (retry_after={retry_after:.0f}s)")
        self.retry_after = retry_after


@dataclass
class VintedItem:
    id: int
    title: str
    price: float
    currency: str
    brand: str | None = None
    size: str | None = None
    status: str | None = None
    photo_url: str | None = None
    photos: list[str] = field(default_factory=list)
    total_price: float | None = None
    total_currency: str | None = None
    url: str = ""
    seller: str | None = None


class VintedClient:
    def __init__(self, base_url: str = "https://www.vinted.fr") -> None:
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "fr-FR,fr;q=0.9",
            }
        )
        self._session_ready = False

    def init_session(self) -> None:
        """Charge la page d'accueil pour récupérer les cookies (dont Datadome) et le token CSRF."""
        logger.info("Initialisation de la session Vinted...")
        response = self.session.get(self.base_url, timeout=15)
        response.raise_for_status()

        csrf_token = self._extract_csrf_token(response.text)
        if csrf_token:
            self.session.headers["X-CSRF-Token"] = csrf_token
        else:
            self.session.headers.pop("X-CSRF-Token", None)
            logger.warning(
                "Impossible d'extraire le token CSRF (structure de la page peut-être "
                "modifiée) : on continue sans, certains appels pourraient échouer."
            )
        self._session_ready = True

    @staticmethod
    def _extract_csrf_token(html: str) -> str | None:
        for pattern in _CSRF_PATTERNS:
            match = pattern.search(html)
            if match:
                return match.group(1)
        return None

    def search(
        self,
        mots_cles: str,
        prix_min: float | None = None,
        prix_max: float | None = None,
        devise: str = "EUR",
        page: int = 1,
        per_page: int = 48,
        order: str = "newest_first",
        filtres_bruts: dict[str, list[str]] | None = None,
    ) -> list[VintedItem]:
        """Recherche des annonces et renvoie une liste de VintedItem (jamais None).

        `filtres_bruts` transmet tels quels des filtres avances (catalog_ids,
        brand_ids, status_ids, size_ids, color_ids, material_ids, ...) : chaque
        cle est le nom du parametre attendu par l'API interne, chaque valeur une
        liste d'ids (verifie en conditions reelles : l'API accepte les valeurs
        multiples sous forme de liste separee par des virgules, ex.
        `status_ids=2,3`).
        """
        if not self._session_ready:
            self.init_session()

        params: dict[str, str | int | float] = {
            "search_text": mots_cles,
            "currency": devise,
            "page": page,
            "per_page": per_page,
            "order": order,
        }
        if prix_min is not None:
            params["price_from"] = prix_min
        if prix_max is not None:
            params["price_to"] = prix_max
        if filtres_bruts:
            for key, values in filtres_bruts.items():
                if values:
                    params[key] = ",".join(str(v) for v in values)

        response = self._get("/api/v2/catalog/items", params)
        return self._parse_items(response)

    def _get(
        self, path: str, params: dict, _retried: bool = False
    ) -> requests.Response:
        url = urljoin(self.base_url, path)
        try:
            response = self.session.get(url, params=params, timeout=15)
        except requests.RequestException as exc:
            raise VintedClientError(f"Erreur réseau lors de l'appel à {path} : {exc}") from exc

        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", 30))
            raise RateLimitError(retry_after)

        if response.status_code in (401, 403):
            if _retried:
                raise VintedClientError(
                    f"Accès refusé ({response.status_code}) par Vinted même après "
                    "renouvellement de la session (Datadome a peut-être détecté le bot)."
                )
            logger.warning(
                "Session rejetée par Vinted (HTTP %s), renouvellement et nouvel essai...",
                response.status_code,
            )
            self._session_ready = False
            self.init_session()
            return self._get(path, params, _retried=True)

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise VintedClientError(f"Erreur HTTP {response.status_code} sur {path}") from exc

        return response

    def _parse_items(self, response: requests.Response) -> list[VintedItem]:
        try:
            data = response.json()
        except ValueError as exc:
            raise VintedClientError("Réponse Vinted non-JSON (structure inattendue)") from exc

        raw_items = data.get("items")
        if raw_items is None:
            logger.warning(
                "Champ 'items' absent de la réponse Vinted : la structure de l'API a "
                "peut-être changé."
            )
            return []

        items: list[VintedItem] = []
        for raw in raw_items:
            try:
                items.append(self._to_item(raw))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Annonce ignorée (champ inattendu) : %s", exc)
        return items

    @staticmethod
    def _extract_montant(raw_price, devise_defaut: str = "EUR") -> tuple[float, str] | None:
        """Lit un champ prix de l'API (`price`, `total_item_price`...), tolerant au format.

        Ces champs arrivent sous forme d'objet `{amount: "9.1", currency_code: "EUR"}`
        (amount est une chaine, pas un nombre) mais on tolere aussi un scalaire brut
        au cas ou l'API change de forme.
        """
        if raw_price is None:
            return None
        if isinstance(raw_price, dict):
            montant = raw_price.get("amount")
            if montant is None:
                return None
            return float(montant), raw_price.get("currency_code", devise_defaut)
        return float(raw_price), devise_defaut

    @staticmethod
    def _extract_photos(raw: dict) -> list[str]:
        """Toutes les photos d'une annonce, deja presentes dans la reponse de recherche

        (champ `photos`, liste) : aucun appel supplementaire a l'API n'est necessaire.
        """
        photos: list[str] = []
        for photo in raw.get("photos") or []:
            if not isinstance(photo, dict):
                continue
            url = photo.get("full_size_url") or photo.get("url")
            if url:
                photos.append(url)
        if not photos:
            single = raw.get("photo") or {}
            url = single.get("full_size_url") or single.get("url")
            if url:
                photos.append(url)
        return photos

    def _to_item(self, raw: dict) -> VintedItem:
        prix = self._extract_montant(raw.get("price")) or (0.0, raw.get("currency", "EUR"))
        total = self._extract_montant(raw.get("total_item_price"))

        photos = self._extract_photos(raw)
        url = raw.get("url") or ""
        if url and not url.startswith("http"):
            url = urljoin(self.base_url, url)

        user = raw.get("user") or {}

        return VintedItem(
            id=int(raw["id"]),
            title=raw.get("title") or "Sans titre",
            price=prix[0],
            currency=prix[1],
            brand=raw.get("brand_title"),
            size=raw.get("size_title"),
            status=raw.get("status"),
            photo_url=photos[0] if photos else None,
            photos=photos,
            total_price=total[0] if total else None,
            total_currency=total[1] if total else None,
            url=url,
            seller=user.get("login"),
        )


if __name__ == "__main__":
    # Test manuel rapide, sans Discord : affiche les dernières annonces trouvées.
    # Lancer avec : python -m src.vinted_client
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    client = VintedClient()
    resultats = client.search("gopro hero 13", prix_max=200)
    print(f"\n{len(resultats)} annonce(s) trouvee(s), 5 dernieres :\n")
    for item in resultats[:5]:
        print(f"- {item.title} - {item.price} {item.currency} - {item.url}")
