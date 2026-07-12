"""
SQLite storage layer for FX candle data.

Design decisions (established in session 1):
- One table per granularity: `candles_D` for daily bars.
- PRIMARY KEY (instrument, time) — acts as a unique constraint.
- INSERT ... ON CONFLICT DO NOTHING — safe idempotent upserts.
- Only complete=True candles are ever stored; the guard is enforced here.
- WAL mode: faster writes, safe for concurrent reads (e.g. from a backtest).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from models import DailyCandle

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_TABLE_DAILY: Final[str] = "candles_D"

_DDL_DAILY: Final[str] = f"""
CREATE TABLE IF NOT EXISTS {_TABLE_DAILY} (
    instrument  TEXT     NOT NULL,
    time        TEXT     NOT NULL,   -- ISO 8601, e.g. "2026-05-19T21:00:00+00:00"
    bid_o       REAL     NOT NULL,
    bid_h       REAL     NOT NULL,
    bid_l       REAL     NOT NULL,
    bid_c       REAL     NOT NULL,
    ask_o       REAL     NOT NULL,
    ask_h       REAL     NOT NULL,
    ask_l       REAL     NOT NULL,
    ask_c       REAL     NOT NULL,
    volume      INTEGER  NOT NULL,
    complete    INTEGER  NOT NULL DEFAULT 1,  -- always 1; kept for schema clarity
    PRIMARY KEY (instrument, time)
);
"""

_SQL_UPSERT: Final[str] = f"""
INSERT INTO {_TABLE_DAILY}
    (instrument, time, bid_o, bid_h, bid_l, bid_c,
     ask_o, ask_h, ask_l, ask_c, volume, complete)
VALUES
    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (instrument, time) DO NOTHING;
"""

_SQL_LATEST_TIME: Final[str] = f"""
SELECT MAX(time) FROM {_TABLE_DAILY} WHERE instrument = ?;
"""

_SQL_COUNT: Final[str] = f"""
SELECT COUNT(*) FROM {_TABLE_DAILY} WHERE instrument = ?;
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db(db_path: Path) -> sqlite3.Connection:
    """
    Open (or create) the SQLite database, apply the schema, and return the
    connection.  Safe to call multiple times — CREATE TABLE IF NOT EXISTS
    is idempotent.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")   # write-ahead log — better concurrency
    conn.execute("PRAGMA synchronous=NORMAL;") # safe with WAL; faster than FULL
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute(_DDL_DAILY)
    conn.commit()
    return conn


def latest_stored_time(
    conn: sqlite3.Connection,
    instrument: str,
) -> datetime | None:
    """
    Return the UTC datetime of the most recent complete candle stored for
    `instrument`, or None if the table is empty for that instrument.
    """
    row = conn.execute(_SQL_LATEST_TIME, (instrument,)).fetchone()
    if row is None or row[0] is None:
        return None
    # SQLite stores the ISO string we inserted; parse it back.
    return datetime.fromisoformat(str(row[0])).replace(tzinfo=timezone.utc)


def upsert_candles(
    conn: sqlite3.Connection,
    instrument: str,
    candles: list[DailyCandle],
) -> int:
    """
    Insert complete candles into `candles_D`.

    - Incomplete candles are silently dropped (belt-and-suspenders guard on
      top of the filter in the fetcher).
    - Duplicate (instrument, time) pairs are silently ignored — safe to call
      repeatedly with overlapping windows.

    Returns the number of rows passed to the DB (including ignored duplicates;
    SQLite does not expose a per-row "was this ignored?" flag cheaply).
    """
    complete_candles = [c for c in candles if c.complete]

    rows = [
        (
            instrument,
            c.time.isoformat(),
            c.bid.o, c.bid.h, c.bid.l, c.bid.c,
            c.ask.o, c.ask.h, c.ask.l, c.ask.c,
            c.volume,
            1,  # complete = True always at this point
        )
        for c in complete_candles
    ]

    conn.executemany(_SQL_UPSERT, rows)
    conn.commit()
    return len(rows)


def candle_count(conn: sqlite3.Connection, instrument: str) -> int:
    """Return the total number of stored candles for `instrument`."""
    row = conn.execute(_SQL_COUNT, (instrument,)).fetchone()
    return int(row[0]) if row else 0