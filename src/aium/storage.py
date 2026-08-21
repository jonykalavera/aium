"""SQLite history storage and status.json cache."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from . import paths
from .models import StatusFile


@contextmanager
def _conn(db: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        yield conn
    finally:
        conn.commit()
        conn.close()


def init_db(db: Path | None = None) -> None:
    db = db or paths.db_file()
    db.parent.mkdir(parents=True, exist_ok=True)
    with _conn(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                balance REAL NOT NULL,
                currency TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_snapshots_provider_ts ON snapshots(provider_id, ts)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quota_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                peak_pct REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_quota_history_provider_ts "
            "ON quota_history(provider_id, ts)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                total_usage REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_history_provider_ts "
            "ON usage_history(provider_id, ts)"
        )


def record_snapshot(
    provider_id: str,
    balance: float,
    currency: str,
    ts: datetime | None = None,
    db: Path | None = None,
) -> None:
    db = db or paths.db_file()
    ts = ts or datetime.now(UTC)
    with _conn(db) as conn:
        conn.execute(
            "INSERT INTO snapshots (provider_id, ts, balance, currency) VALUES (?, ?, ?, ?)",
            (provider_id, ts.isoformat(), balance, currency),
        )


def get_snapshots(
    provider_id: str, since: datetime | None = None, db: Path | None = None
) -> list[tuple[datetime, float]]:
    db = db or paths.db_file()
    query = "SELECT ts, balance FROM snapshots WHERE provider_id = ?"
    params: list[object] = [provider_id]
    if since is not None:
        query += " AND ts >= ?"
        params.append(since.isoformat())
    query += " ORDER BY ts ASC"
    with _conn(db) as conn:
        rows = conn.execute(query, params).fetchall()
    return [(datetime.fromisoformat(r[0]), r[1]) for r in rows]


def record_quota(
    provider_id: str,
    peak_pct: float,
    ts: datetime | None = None,
    db: Path | None = None,
) -> None:
    db = db or paths.db_file()
    ts = ts or datetime.now(UTC)
    with _conn(db) as conn:
        conn.execute(
            "INSERT INTO quota_history (provider_id, ts, peak_pct) VALUES (?, ?, ?)",
            (provider_id, ts.isoformat(), peak_pct),
        )


def get_quota_history(provider_id: str, limit: int = 30, db: Path | None = None) -> list[float]:
    db = db or paths.db_file()
    with _conn(db) as conn:
        rows = conn.execute(
            "SELECT peak_pct FROM quota_history WHERE provider_id = ? ORDER BY ts ASC",
            (provider_id,),
        ).fetchall()
    return [r[0] for r in rows[-limit:]]


def get_spend_sparkline(provider_id: str, limit: int = 30, db: Path | None = None) -> list[float]:
    """Spend per interval = positive balance deltas between consecutive snapshots."""
    snapshots = get_snapshots(provider_id, db=db)
    deltas: list[float] = []
    for (_, prev), (_, cur) in zip(snapshots, snapshots[1:], strict=False):
        spend = prev - cur
        deltas.append(max(0.0, round(spend, 4)))
    return deltas[-limit:]


def record_usage(
    provider_id: str,
    total_usage: float,
    ts: datetime | None = None,
    db: Path | None = None,
) -> None:
    db = db or paths.db_file()
    ts = ts or datetime.now(UTC)
    with _conn(db) as conn:
        conn.execute(
            "INSERT INTO usage_history (provider_id, ts, total_usage) VALUES (?, ?, ?)",
            (provider_id, ts.isoformat(), total_usage),
        )


def get_usage_history(provider_id: str, db: Path | None = None) -> list[tuple[datetime, float]]:
    db = db or paths.db_file()
    with _conn(db) as conn:
        rows = conn.execute(
            "SELECT ts, total_usage FROM usage_history WHERE provider_id = ? ORDER BY ts ASC",
            (provider_id,),
        ).fetchall()
    return [(datetime.fromisoformat(r[0]), r[1]) for r in rows]


def get_usage_sparkline(provider_id: str, limit: int = 30, db: Path | None = None) -> list[float]:
    """Spend per interval = increases of the cumulative usage between records."""
    history = get_usage_history(provider_id, db=db)
    deltas: list[float] = []
    for (_, prev), (_, cur) in zip(history, history[1:], strict=False):
        deltas.append(max(0.0, round(cur - prev, 4)))
    return deltas[-limit:]


def write_status(status: StatusFile, status_path: Path | None = None) -> None:
    status_path = status_path or paths.status_file()
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(status.model_dump_json(indent=2))


def read_status(status_path: Path | None = None) -> StatusFile | None:
    status_path = status_path or paths.status_file()
    if not status_path.exists():
        return None
    try:
        return StatusFile.model_validate_json(status_path.read_text())
    except json.JSONDecodeError, ValueError:
        return None
