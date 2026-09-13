"""Point d'entree : lance la CLI si des arguments sont fournis, sinon demarre la surveillance."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.cli import CLI_COMMANDS, build_parser
from src.notifier import DiscordNotifier
from src.scheduler import run_forever
from src.searches import load_searches
from src.storage import init_db

LOG_PATH = "logs/vinted_watcher.log"


def _setup_logging() -> None:
    Path(LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def main() -> None:
    _setup_logging()
    load_dotenv()

    if len(sys.argv) > 1 and sys.argv[1] in CLI_COMMANDS:
        parser = build_parser()
        args = parser.parse_args()
        args.func(args)
        return

    init_db()

    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logging.error(
            "DISCORD_WEBHOOK_URL manquant. Copie .env.example vers .env et renseigne "
            "l'URL du webhook Discord avant de lancer la surveillance."
        )
        sys.exit(1)

    notifier = DiscordNotifier(webhook_url)
    searches = load_searches()
    if not searches:
        logging.warning(
            "Aucune recherche dans config/searches.json. Utilise 'python main.py add "
            "--nom ... --mots-cles ...' pour en ajouter une."
        )
        return

    run_forever(searches, notifier)


if __name__ == "__main__":
    main()
