"""SQLite persistence for sources and user settings."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .sources import BUILTIN_SOURCES, SECTIONS

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    url             TEXT NOT NULL UNIQUE,
    feed_url        TEXT,
    kind            TEXT NOT NULL DEFAULT 'feed',   -- feed | page | article
    section         TEXT NOT NULL DEFAULT 'custom',
    enabled         INTEGER NOT NULL DEFAULT 1,
    builtin         INTEGER NOT NULL DEFAULT 0,
    weight          REAL NOT NULL DEFAULT 1.0,
    created_at      TEXT NOT NULL,
    last_fetched_at TEXT,
    last_status     TEXT,
    last_count      INTEGER,
    consumed_at     TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS: dict[str, Any] = {
    "voice": "kokoro:af_heart",
    "speed": 1.0,
    "briefing_time": "06:30",
    "auto_generate": True,
    "stories": {"canada": 6, "tech": 6, "custom": 4},
    "city": "Toronto",
    "latitude": 43.6532,
    "longitude": -79.3832,
    "weather": True,
}

SOURCE_FIELDS = (
    "id", "name", "url", "feed_url", "kind", "section", "enabled", "builtin", "weight",
    "created_at", "last_fetched_at", "last_status", "last_count", "consumed_at",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)
        self.seed()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _run(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock, self._conn() as c:
            return c.execute(sql, params)

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock, self._conn() as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    # ------------------------------------------------------------------ sources
    def seed(self) -> None:
        # INSERT OR IGNORE keeps user toggles and lets new built-ins appear on upgrade.
        for s in BUILTIN_SOURCES:
            self._run(
                "INSERT OR IGNORE INTO sources (name, url, feed_url, kind, section, builtin, weight, created_at)"
                " VALUES (?, ?, ?, 'feed', ?, 1, ?, ?)",
                (s["name"], s["url"], s["url"], s["section"], s.get("weight", 1.0), now_iso()),
            )

    def list_sources(self) -> list[dict]:
        rows = self._all("SELECT * FROM sources ORDER BY builtin DESC, section, name")
        for r in rows:
            r["enabled"] = bool(r["enabled"])
            r["builtin"] = bool(r["builtin"])
        return rows

    def get_source(self, source_id: int) -> dict | None:
        rows = self._all("SELECT * FROM sources WHERE id = ?", (source_id,))
        if not rows:
            return None
        r = rows[0]
        r["enabled"] = bool(r["enabled"])
        r["builtin"] = bool(r["builtin"])
        return r

    def active_sources(self) -> list[dict]:
        """Sources to pull for the next briefing (single articles only until used once)."""
        return [
            s for s in self.list_sources()
            if s["enabled"] and not (s["kind"] == "article" and s["consumed_at"])
        ]

    def add_source(self, *, name: str, url: str, feed_url: str | None, kind: str, section: str) -> dict:
        if section not in SECTIONS:
            raise ValueError(f"Unknown section: {section}")
        cur = self._run(
            "INSERT INTO sources (name, url, feed_url, kind, section, builtin, weight, created_at)"
            " VALUES (?, ?, ?, ?, ?, 0, 1.2, ?)",
            (name, url, feed_url, kind, section, now_iso()),
        )
        return self.get_source(cur.lastrowid)  # type: ignore[return-value]

    def update_source(self, source_id: int, **fields: Any) -> dict | None:
        allowed = {"name", "section", "enabled", "last_fetched_at", "last_status", "last_count", "consumed_at"}
        sets = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "section" in sets and sets["section"] not in SECTIONS:
            raise ValueError(f"Unknown section: {sets['section']}")
        if "enabled" in sets:
            sets["enabled"] = int(bool(sets["enabled"]))
            if sets["enabled"]:
                sets["consumed_at"] = None  # re-enabling a used article queues it again
        if sets:
            cols = ", ".join(f"{k} = ?" for k in sets)
            self._run(f"UPDATE sources SET {cols} WHERE id = ?", (*sets.values(), source_id))
        return self.get_source(source_id)

    def mark_consumed(self, source_id: int) -> None:
        self._run("UPDATE sources SET consumed_at = ?, enabled = 0 WHERE id = ?", (now_iso(), source_id))

    def delete_source(self, source_id: int) -> bool:
        src = self.get_source(source_id)
        if not src or src["builtin"]:
            return False
        self._run("DELETE FROM sources WHERE id = ?", (source_id,))
        return True

    def source_exists(self, url: str) -> bool:
        return bool(self._all("SELECT 1 FROM sources WHERE url = ? OR feed_url = ?", (url, url)))

    # ----------------------------------------------------------------- settings
    def get_settings(self) -> dict[str, Any]:
        stored = {r["key"]: json.loads(r["value"]) for r in self._all("SELECT key, value FROM settings")}
        merged = {**DEFAULT_SETTINGS, **stored}
        merged["stories"] = {**DEFAULT_SETTINGS["stories"], **(stored.get("stories") or {})}
        return merged

    def update_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        for key, value in values.items():
            if key not in DEFAULT_SETTINGS:
                continue
            self._run(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )
        return self.get_settings()
