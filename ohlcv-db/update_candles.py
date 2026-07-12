"""
FX Candle Updater — full-history backfill and incremental daily update
for all 28 major FX pairs.

FIRST RUN  — backfills all available Oanda history (back to ~2003 for majors).
             Expect ~5 800 candles × 28 instruments = ~162 000 rows.
             Runtime: a few minutes on a normal internet connection.

DAILY RUN  — fetches only candles newer than the latest row already stored.
             Run this after the NY 17:00 close each weekday:
               - NY summer (EDT): after 05:00 HKT
               - NY winter (EST): after 06:00 HKT

SCHEDULING (cron, Hong Kong time — adjust for summer/winter manually)
----------------------------------------------------------------------
    # Run at 05:30 HKT every weekday (safe for NY summer; add 1h in winter)
    30 5 * * 1-5 cd /path/to/project && python update_candles.py >> candles.log 2>&1

ENVIRONMENT VARIABLES REQUIRED
-------------------------------
    OANDA_API_TOKEN   — your Oanda v20 personal access token
    OANDA_ACCOUNT_ID  — your Oanda account ID

IDEMPOTENCY
-----------
Running this script multiple times is always safe.
The DB upsert silently ignores duplicate (instrument, time) pairs.

IMPORTANT RISK NOTE
-------------------
These 28 pairs are NOT 28 independent bets.  EUR, GBP, AUD, NZD pairs are
highly correlated.  When a strategy fails, it will fail across a whole
currency cluster simultaneously.  Never forget this when sizing positions.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final
from dotenv import load_dotenv

import sqlite3

from db import candle_count, init_db, latest_stored_time, upsert_candles
from fetcher import fetch_all_daily_candles

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# All 28 major FX pairs in Oanda's underscore notation.
# Source: info-about-antony-the-algo-trader.md
INSTRUMENTS: Final[list[str]] = [
    "EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF",
    "AUD_USD", "USD_CAD", "NZD_USD",
    "EUR_GBP", "EUR_JPY", "EUR_CHF", "EUR_CAD", "EUR_AUD", "EUR_NZD",
    "GBP_JPY", "GBP_CHF", "GBP_CAD", "GBP_AUD", "GBP_NZD",
    "AUD_JPY", "AUD_CHF", "AUD_CAD", "AUD_NZD",
    "NZD_JPY", "NZD_CHF", "NZD_CAD",
    "CAD_JPY", "CAD_CHF",
    "CHF_JPY",
]

# Earliest date Oanda has data for major pairs (~2003).
# We deliberately go earlier than necessary; Oanda simply returns what it has.
HISTORY_START: Final[datetime] = datetime(2003, 1, 1, tzinfo=timezone.utc)

DB_PATH: Final[Path] = Path("fx_candles.db")


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _update_one(conn: sqlite3.Connection, instrument: str) -> None:
    """
    Backfill or incrementally update one instrument.

    First run  (no rows in DB for this instrument):
        Fetches from HISTORY_START — paginating through the full Oanda archive.

    Subsequent runs:
        Fetches only from (latest stored candle time + 1 second) onwards.
        The +1 second avoids re-requesting a candle we already have, but even
        without it the ON CONFLICT DO NOTHING guard makes it safe.
    """
    latest = latest_stored_time(conn, instrument)

    if latest is None:
        from_dt = HISTORY_START
        mode = f"BACKFILL from {from_dt.date()} (full Oanda history)"
    else:
        from_dt = latest + timedelta(seconds=1)
        mode = f"INCREMENTAL from {latest.date()}"

    print(f"  [{instrument}] {mode} ...", flush=True)

    candles = fetch_all_daily_candles(instrument, from_dt=from_dt)

    if not candles:
        print(f"  [{instrument}] No new complete candles — already up to date.")
        return

    inserted = upsert_candles(conn, instrument, candles)
    total = candle_count(conn, instrument)

    print(
        f"  [{instrument}] "
        f"Fetched {len(candles):>5} candle(s), "
        f"upserted {inserted:>5} to DB, "
        f"total stored: {total:>6}, "
        f"latest: {candles[-1].time.date()}"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    load_dotenv()  # reads .env from the current directory into os.environ

    print(f"DB: {DB_PATH.resolve()}")
    print(f"Instruments: {len(INSTRUMENTS)} pairs\n")

    conn = init_db(DB_PATH)
    errors: list[str] = []

    for instrument in INSTRUMENTS:
        try:
            _update_one(conn, instrument)
        except Exception as exc:  # noqa: BLE001
            # Continue with remaining instruments even if one fails.
            # A single bad instrument (e.g. not available on practice account)
            # must not abort the whole run.
            msg = f"[{instrument}] FAILED: {exc}"
            print(f"  ERROR: {msg}", file=sys.stderr)
            errors.append(msg)

    conn.close()

    print()
    if errors:
        print(f"{len(errors)} instrument(s) failed:")
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"All {len(INSTRUMENTS)} instruments updated successfully.")


if __name__ == "__main__":
    main()