"""Persistance SQLite des annonces deja vues, pour eviter les doublons de notification."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .vinted_client import VintedItem

DEFAULT_DB_PATH = "data/seen_items.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_items (
    search_id TEXT NOT NULL,
    item_id INTEGER NOT NULL,
    title TEXT,
    price REAL,
    first_seen_at TEXT NOT NULL,
    PRIMARY KEY (search_id, item_id)
);
"""

_db_path = DEFAULT_DB_PATH


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    global _db_path
    _db_path = db_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(_SCHEMA)


@contextmanager
def _connect():
    conn = sqlite3.connect(_db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def is_new(search_id: str, item_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM seen_items WHERE search_id = ? AND item_id = ?",
            (search_id, item_id),
        ).fetchone()
    return row is None


def mark_seen(search_id: str, item: VintedItem) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO seen_items (search_id, item_id, title, price, first_seen_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (search_id, item.id, item.title, item.price, datetime.now(timezone.utc).isoformat()),
        )


def is_search_known(search_id: str) -> bool:
    """Indique si cette recherche a deja au moins une annonce enregistree (donc deja verifiee une fois)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM seen_items WHERE search_id = ? LIMIT 1", (search_id,)
        ).fetchone()
    return row is not None
