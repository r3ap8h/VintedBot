"""Interface web locale de gestion des recherches et des webhooks.

Process separe du scheduler (`main.py`) : les deux partagent config/searches.json
(ecriture atomique, rechargee periodiquement par le scheduler) et data/seen_items.db.

Ecoute uniquement sur 127.0.0.1 : ce serveur n'a AUCUNE authentification, il ne
doit jamais etre expose au-dela de cette machine (il permet de lire/modifier les
webhooks Discord configures).

Lancement : python -m src.webapp   (ou : uvicorn src.webapp:app --reload)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .notifier import DiscordNotifier, mask_webhook_url
from .searches import (
    add_search,
    add_search_from_url,
    get_search,
    load_searches,
    remove_search,
    summarize_filtres,
    update_search,
)
from .storage import get_last_seen_at, get_recent, init_db
from .url_parser import parse_vinted_search_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

load_dotenv()
init_db()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Vinted Watcher")


def _default_webhook_url() -> str | None:
    return os.getenv("DISCORD_WEBHOOK_URL")


def _flash_from_query(request: Request) -> dict | None:
    message = request.query_params.get("flash")
    flash_type = request.query_params.get("flash_type", "ok")
    if not message:
        return None
    return {"type": flash_type, "message": message}


def _redirect_with_flash(url: str, message: str, flash_type: str = "ok") -> RedirectResponse:
    from urllib.parse import urlencode

    query = urlencode({"flash": message, "flash_type": flash_type})
    return RedirectResponse(url=f"{url}?{query}", status_code=303)


def _enrichir_recherche(search) -> dict:
    return {
        "search": search,
        "filtres_resume": summarize_filtres(search.filtres_bruts),
        "webhook_masque": mask_webhook_url(search.webhook_url) if search.webhook_url else "(webhook global)",
        "derniere_activite": get_last_seen_at(search.id),
    }


@app.get("/")
def index(request: Request):
    recherches = [_enrichir_recherche(s) for s in load_searches()]
    return templates.TemplateResponse(
        request,
        "index.html",
        {"recherches": recherches, "flash": _flash_from_query(request)},
    )


@app.get("/searches/new")
def new_search_form(request: Request, mode: str = "simple"):
    mode = mode if mode in ("simple", "url") else "simple"
    return templates.TemplateResponse(
        request,
        "add.html",
        {"mode": mode, "form": {}, "preview": None, "erreur": None, "flash": _flash_from_query(request)},
    )


@app.post("/searches/new/simple")
def create_simple_search(
    nom: str = Form(...),
    mots_cles: str = Form(...),
    prix_min: float | None = Form(None),
    prix_max: float | None = Form(None),
    intervalle_minutes: int = Form(3),
    webhook: str = Form(""),
):
    search = add_search(
        nom=nom,
        mots_cles=mots_cles,
        prix_min=prix_min,
        prix_max=prix_max,
        intervalle_minutes=intervalle_minutes,
        webhook_url=webhook.strip() or None,
    )
    return _redirect_with_flash("/", f"Recherche '{search.nom}' ajoutee.")


@app.post("/searches/preview-url")
def preview_url(
    request: Request,
    nom: str = Form(...),
    url: str = Form(...),
    intervalle_minutes: int = Form(3),
    webhook: str = Form(""),
):
    form = {"nom": nom, "url": url, "intervalle_minutes": intervalle_minutes, "webhook": webhook}
    try:
        parsed = parse_vinted_search_url(url)
        preview = {
            "mots_cles": parsed.mots_cles,
            "prix_min": parsed.prix_min,
            "prix_max": parsed.prix_max,
            "devise": parsed.devise,
            "filtres_bruts": parsed.filtres_bruts,
        }
        erreur = None
    except ValueError as exc:
        preview = None
        erreur = f"Impossible d'analyser cette URL : {exc}"

    return templates.TemplateResponse(
        request,
        "add.html",
        {"mode": "url", "form": form, "preview": preview, "erreur": erreur, "flash": None},
    )


@app.post("/searches/new/from-url")
def create_search_from_url(
    nom: str = Form(...),
    url: str = Form(...),
    intervalle_minutes: int = Form(3),
    webhook: str = Form(""),
):
    search = add_search_from_url(
        nom=nom,
        url=url,
        intervalle_minutes=intervalle_minutes,
        webhook_url=webhook.strip() or None,
    )
    return _redirect_with_flash("/", f"Recherche '{search.nom}' ajoutee depuis l'URL Vinted.")


@app.get("/searches/{search_id}/edit")
def edit_search_form(request: Request, search_id: str):
    search = get_search(search_id)
    if search is None:
        return _redirect_with_flash("/", f"Recherche '{search_id}' introuvable.", "erreur")
    return templates.TemplateResponse(
        request,
        "edit.html",
        {
            "search": search,
            "filtres_resume": summarize_filtres(search.filtres_bruts),
            "webhook_masque": mask_webhook_url(search.webhook_url) if search.webhook_url else "(webhook global)",
            "flash": _flash_from_query(request),
        },
    )


@app.post("/searches/{search_id}/edit")
def edit_search_submit(
    search_id: str,
    nom: str = Form(...),
    mots_cles: str = Form(""),
    prix_min: float | None = Form(None),
    prix_max: float | None = Form(None),
    intervalle_minutes: int = Form(3),
    webhook: str = Form(""),
    actif: str = Form("true"),
):
    try:
        update_search(
            search_id,
            nom=nom,
            mots_cles=mots_cles,
            prix_min=prix_min,
            prix_max=prix_max,
            intervalle_minutes=intervalle_minutes,
            webhook_url=webhook.strip() or None,
            actif=(actif == "true"),
        )
        return _redirect_with_flash("/", f"Recherche '{nom}' mise a jour.")
    except ValueError as exc:
        return _redirect_with_flash("/", str(exc), "erreur")


@app.post("/searches/{search_id}/toggle")
def toggle_search(search_id: str):
    search = get_search(search_id)
    if search is None:
        return _redirect_with_flash("/", f"Recherche '{search_id}' introuvable.", "erreur")
    update_search(search_id, actif=not search.actif)
    etat = "desactivee" if search.actif else "activee"
    return _redirect_with_flash("/", f"Recherche '{search.nom}' {etat}.")


@app.get("/searches/{search_id}/delete")
def delete_search_confirm(request: Request, search_id: str):
    search = get_search(search_id)
    if search is None:
        return _redirect_with_flash("/", f"Recherche '{search_id}' introuvable.", "erreur")
    return templates.TemplateResponse(request, "delete_confirm.html", {"search": search, "flash": None})


@app.post("/searches/{search_id}/delete")
def delete_search_submit(search_id: str):
    try:
        remove_search(search_id)
        return _redirect_with_flash("/", f"Recherche '{search_id}' supprimee.")
    except ValueError as exc:
        return _redirect_with_flash("/", str(exc), "erreur")


@app.get("/webhooks")
def webhooks_page(request: Request):
    webhook_global = _default_webhook_url()
    recherches_avec_webhook = [
        _enrichir_recherche(s) for s in load_searches() if s.webhook_url
    ]
    return templates.TemplateResponse(
        request,
        "webhooks.html",
        {
            "webhook_global_masque": mask_webhook_url(webhook_global) if webhook_global else None,
            "recherches_avec_webhook": recherches_avec_webhook,
            "flash": _flash_from_query(request),
        },
    )


@app.post("/webhooks/test")
def test_webhook(cible: str = Form(...)):
    from .vinted_client import VintedItem

    if cible == "global":
        webhook_url = _default_webhook_url()
        libelle = "webhook global"
    elif cible.startswith("search:"):
        search = get_search(cible.removeprefix("search:"))
        if search is None or not search.webhook_url:
            return _redirect_with_flash("/webhooks", "Recherche ou webhook introuvable.", "erreur")
        webhook_url = search.webhook_url
        libelle = f"webhook de '{search.nom}'"
    else:
        return _redirect_with_flash("/webhooks", "Cible de test invalide.", "erreur")

    if not webhook_url:
        return _redirect_with_flash("/webhooks", "Aucun webhook global configure dans .env.", "erreur")

    item_test = VintedItem(
        id=0,
        title="Message de test - Vinted Watcher",
        price=0.0,
        currency="EUR",
        url="https://www.vinted.fr/",
    )
    succes = DiscordNotifier(webhook_url).notify(item_test, "Test webhook")
    if succes:
        return _redirect_with_flash("/webhooks", f"Message de test envoye avec succes ({libelle}).")
    return _redirect_with_flash("/webhooks", f"Echec de l'envoi du message de test ({libelle}), voir les logs.", "erreur")


@app.get("/history")
def history_page(request: Request):
    searches_by_id = {s.id: s.nom for s in load_searches()}
    items = get_recent(limit=50)
    for it in items:
        it["search_nom"] = searches_by_id.get(it["search_id"], it["search_id"])
    return templates.TemplateResponse(
        request, "history.html", {"items": items, "flash": _flash_from_query(request)}
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.webapp:app", host="127.0.0.1", port=8000, reload=True)
