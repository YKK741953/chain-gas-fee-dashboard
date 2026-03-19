from __future__ import annotations

import sqlite3
import threading
import time
from functools import lru_cache
from pathlib import Path

from ..config import get_settings


class HistoryStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=30)

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS gas_price_history (
                    id INTEGER PRIMARY KEY,
                    chain_key TEXT NOT NULL,
                    observed_at INTEGER NOT NULL,
                    gas_price_wei INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_gas_price_history_chain_observed_at
                ON gas_price_history (chain_key, observed_at)
                """
            )
            connection.commit()

    def latest_observed_at(self, chain_key: str, mode: str = "standard") -> int | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT observed_at
                FROM gas_price_history
                WHERE chain_key = ? AND mode = ?
                ORDER BY observed_at DESC
                LIMIT 1
                """,
                (chain_key, mode),
            ).fetchone()
        return int(row[0]) if row else None

    def insert_gas_price(
        self,
        chain_key: str,
        observed_at: int,
        gas_price_wei: int,
        mode: str = "standard",
    ) -> None:
        created_at = int(time.time())
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO gas_price_history (
                    chain_key,
                    observed_at,
                    gas_price_wei,
                    mode,
                    created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (chain_key, observed_at, gas_price_wei, mode, created_at),
            )
            connection.commit()

    def fetch_gas_prices_since(
        self,
        chain_key: str,
        since_ts: int,
        mode: str = "standard",
    ) -> list[tuple[int, int]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT observed_at, gas_price_wei
                FROM gas_price_history
                WHERE chain_key = ? AND mode = ? AND observed_at >= ?
                ORDER BY observed_at ASC
                """,
                (chain_key, mode, since_ts),
            ).fetchall()
        return [(int(observed_at), int(gas_price_wei)) for observed_at, gas_price_wei in rows]

    def prune_before(self, cutoff_ts: int) -> int:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM gas_price_history WHERE observed_at < ?",
                (cutoff_ts,),
            )
            connection.commit()
        return int(cursor.rowcount)


@lru_cache(maxsize=1)
def get_history_store() -> HistoryStore:
    settings = get_settings()
    return HistoryStore(settings.relative_index_db_path)


def reset_history_store() -> None:
    get_history_store.cache_clear()
