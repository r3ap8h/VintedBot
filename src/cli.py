"""Interface en ligne de commande pour gerer les recherches sans editer le JSON a la main."""

from __future__ import annotations

import argparse

from .notifier import mask_webhook_url
from .searches import (
    add_search,
    add_search_from_url,
    load_searches,
    remove_search,
    set_active,
    summarize_filtres,
)

CLI_COMMANDS = {"add", "add-url", "list", "enable", "disable", "remove"}


def handle_add(args: argparse.Namespace) -> None:
    search = add_search(
        nom=args.nom,
        mots_cles=args.mots_cles,
        prix_min=args.prix_min,
        prix_max=args.prix_max,
        devise=args.devise,
        intervalle_minutes=args.intervalle_minutes,
        webhook_url=args.webhook,
    )
    print(f"Recherche ajoutee : {search.id} ({search.nom})")


def handle_add_url(args: argparse.Namespace) -> None:
    search = add_search_from_url(
        nom=args.nom,
        url=args.url,
        intervalle_minutes=args.intervalle_minutes,
        webhook_url=args.webhook,
    )
    print(f"Recherche ajoutee : {search.id} ({search.nom})")
    print("Resume de ce qui a ete compris depuis l'URL :")
    print(f"  mots-cles : '{search.mots_cles}' (vide = recherche basee uniquement sur les filtres)")
    print(f"  prix min  : {search.prix_min if search.prix_min is not None else 'aucun'}")
    print(f"  prix max  : {search.prix_max if search.prix_max is not None else 'aucun'}")
    print(f"  devise    : {search.devise}")
    if search.filtres_bruts:
        print("  filtres avances :")
        for cle, valeurs in search.filtres_bruts.items():
            print(f"    - {cle} = {','.join(valeurs)}")
    else:
        print("  filtres avances : aucun detecte")
    print("Verifie que ce resume correspond bien a ta recherche avant de laisser tourner la surveillance.")


def handle_list(args: argparse.Namespace) -> None:
    searches = load_searches()
    if not searches:
        print("Aucune recherche configuree.")
        return
    for s in searches:
        etat = "actif" if s.actif else "inactif"
        prix_min = "" if s.prix_min is None else str(s.prix_min)
        prix_max = "" if s.prix_max is None else str(s.prix_max)
        prix = f"{prix_min}-{prix_max}".strip("-") or "sans limite"
        webhook = mask_webhook_url(s.webhook_url) if s.webhook_url else "(webhook global)"
        ligne = (
            f"[{etat}] {s.id} - {s.nom} - '{s.mots_cles}' - {prix} {s.devise} "
            f"- toutes les {s.intervalle_minutes} min - webhook: {webhook}"
        )
        filtres = summarize_filtres(s.filtres_bruts)
        if filtres:
            ligne += f" - filtres: {filtres}"
        print(ligne)


def handle_enable(args: argparse.Namespace) -> None:
    set_active(args.id, True)
    print(f"Recherche '{args.id}' activee.")


def handle_disable(args: argparse.Namespace) -> None:
    set_active(args.id, False)
    print(f"Recherche '{args.id}' desactivee.")


def handle_remove(args: argparse.Namespace) -> None:
    remove_search(args.id)
    print(f"Recherche '{args.id}' supprimee.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py", description="Vinted Watcher — gestion des recherches"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_add = subparsers.add_parser("add", help="Ajouter une recherche simple (mots-cles + prix)")
    p_add.add_argument("--nom", required=True)
    p_add.add_argument("--mots-cles", required=True, dest="mots_cles")
    p_add.add_argument("--prix-min", type=float, default=None, dest="prix_min")
    p_add.add_argument("--prix-max", type=float, default=None, dest="prix_max")
    p_add.add_argument("--devise", default="EUR")
    p_add.add_argument(
        "--intervalle-minutes", type=int, default=3, dest="intervalle_minutes"
    )
    p_add.add_argument(
        "--webhook", default=None, help="Webhook Discord dedie (sinon le webhook global de .env)"
    )
    p_add.set_defaults(func=handle_add)

    p_add_url = subparsers.add_parser(
        "add-url", help="Ajouter une recherche a partir d'une URL Vinted (filtres avances)"
    )
    p_add_url.add_argument("--nom", required=True)
    p_add_url.add_argument("--url", required=True, help="URL de recherche/catalogue copiee sur vinted.fr")
    p_add_url.add_argument(
        "--intervalle-minutes", type=int, default=3, dest="intervalle_minutes"
    )
    p_add_url.add_argument(
        "--webhook", default=None, help="Webhook Discord dedie (sinon le webhook global de .env)"
    )
    p_add_url.set_defaults(func=handle_add_url)

    p_list = subparsers.add_parser("list", help="Lister les recherches")
    p_list.set_defaults(func=handle_list)

    p_enable = subparsers.add_parser("enable", help="Activer une recherche")
    p_enable.add_argument("id")
    p_enable.set_defaults(func=handle_enable)

    p_disable = subparsers.add_parser("disable", help="Desactiver une recherche")
    p_disable.add_argument("id")
    p_disable.set_defaults(func=handle_disable)

    p_remove = subparsers.add_parser("remove", help="Supprimer une recherche")
    p_remove.add_argument("id")
    p_remove.set_defaults(func=handle_remove)

    return parser
