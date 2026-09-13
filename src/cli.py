"""Interface en ligne de commande pour gerer les recherches sans editer le JSON a la main."""

from __future__ import annotations

import argparse

from .searches import add_search, load_searches, remove_search, set_active

CLI_COMMANDS = {"add", "list", "enable", "disable", "remove"}


def handle_add(args: argparse.Namespace) -> None:
    search = add_search(
        nom=args.nom,
        mots_cles=args.mots_cles,
        prix_min=args.prix_min,
        prix_max=args.prix_max,
        devise=args.devise,
        intervalle_minutes=args.intervalle_minutes,
    )
    print(f"Recherche ajoutee : {search.id} ({search.nom})")


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
        print(
            f"[{etat}] {s.id} - {s.nom} - '{s.mots_cles}' - {prix} {s.devise} "
            f"- toutes les {s.intervalle_minutes} min"
        )


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

    p_add = subparsers.add_parser("add", help="Ajouter une recherche")
    p_add.add_argument("--nom", required=True)
    p_add.add_argument("--mots-cles", required=True, dest="mots_cles")
    p_add.add_argument("--prix-min", type=float, default=None, dest="prix_min")
    p_add.add_argument("--prix-max", type=float, default=None, dest="prix_max")
    p_add.add_argument("--devise", default="EUR")
    p_add.add_argument(
        "--intervalle-minutes", type=int, default=3, dest="intervalle_minutes"
    )
    p_add.set_defaults(func=handle_add)

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
