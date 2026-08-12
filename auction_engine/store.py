from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import AnalysisResult, Comparable, analysis_from_dict


class EngineStore:
    def __init__(self, path: str):
        target: str | Path = path
        if path != ":memory:":
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(target, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.connection:
            self.connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                CREATE TABLE IF NOT EXISTS market_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS analysis_results (
                    item_id TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (item_id, config_hash)
                );
                """
            )

    def get_comps(self, cache_key: str) -> list[Comparable] | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT payload, expires_at FROM market_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()
        if not row or datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            return None
        return [Comparable(**entry) for entry in json.loads(row["payload"])]

    def put_comps(self, cache_key: str, comps: list[Comparable], ttl_hours: int) -> None:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=ttl_hours)
        payload = json.dumps([comp.__dict__ for comp in comps], separators=(",", ":"))
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO market_cache(cache_key,payload,expires_at,updated_at) VALUES(?,?,?,?)",
                (cache_key, payload, expires.isoformat(), now.isoformat()),
            )

    def has_result(self, item_id: str, config_hash: str) -> bool:
        with self.lock:
            return self.connection.execute(
                "SELECT 1 FROM analysis_results WHERE item_id = ? AND config_hash = ?", (item_id, config_hash)
            ).fetchone() is not None

    def get_result(self, item_id: str, config_hash: str) -> AnalysisResult | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT payload FROM analysis_results WHERE item_id = ? AND config_hash = ?", (item_id, config_hash)
            ).fetchone()
        return analysis_from_dict(json.loads(row["payload"])) if row else None

    def put_result(self, result: AnalysisResult, config_hash: str) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO analysis_results(item_id,config_hash,payload,updated_at) VALUES(?,?,?,?)",
                (result.item.item_id, config_hash, json.dumps(result.to_dict(), separators=(",", ":")), result.analyzed_at),
            )

    def close(self) -> None:
        with self.lock:
            self.connection.close()
