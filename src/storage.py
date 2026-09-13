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


def get_last_seen_at(search_id: str) -> str | None:
    """Date de la derniere annonce enregistree pour cette recherche (approximation de son activite)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT MAX(first_seen_at) FROM seen_items WHERE search_id = ?", (search_id,)
        ).fetchone()
    return row[0] if row else None


def get_recent(limit: int = 50) -> list[dict]:
    """Dernieres annonces enregistrees, toutes recherches confondues (pour l'historique)."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT search_id, item_id, title, price, first_seen_at
            FROM seen_items
            ORDER BY first_seen_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "search_id": r[0],
            "item_id": r[1],
            "title": r[2],
            "price": r[3],
            "first_seen_at": r[4],
        }
        for r in rows
    ]
