"""
Fetch one week of daily BA (bid & ask) candles for EURUSD from Oanda v20 API.

Prerequisites
-------------
    pip install oandapyV20

Environment variables required
-------------------------------
    OANDA_API_TOKEN  – your Oanda v20 personal access token
    OANDA_ACCOUNT_ID – your Oanda account ID (e.g. "101-004-XXXXXXX-001")

Run
---
    python fetch_eurusd_candles.py
"""

from __future__ import annotations

import os
from dotenv import load_dotenv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Final

import oandapyV20
import oandapyV20.endpoints.instruments as v20instruments

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INSTRUMENT: Final[str] = "EUR_USD"
GRANULARITY: Final[str] = "D"
PRICE: Final[str] = "BA"          # bid AND ask
DAILY_ALIGNMENT: Final[int] = 17  # 17:00 New York — global FX convention
ALIGNMENT_TZ: Final[str] = "America/New_York"
ENVIRONMENT: Final[str] = "practice"  # "practice" = demo; "live" = live

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OhlcHalf:
    """OHLC values for one side of the spread (bid OR ask)."""
    o: float
    h: float
    l: float  # noqa: E741  (short name is conventional here)
    c: float


@dataclass(frozen=True)
class DailyCandle:
    """One complete daily BA candle."""
    time: datetime     # UTC, timezone-aware
    bid: OhlcHalf
    ask: OhlcHalf
    volume: int
    complete: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

load_dotenv()  # reads .env from the current directory into os.environ

def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{name}' is not set. "
            "Add it to your shell profile or .env file — never hard-code credentials."
        )
    return value


def _parse_ohlc(raw: dict[str, str]) -> OhlcHalf:
    return OhlcHalf(
        o=float(raw["o"]),
        h=float(raw["h"]),
        l=float(raw["l"]),
        c=float(raw["c"]),
    )


def _parse_candle(raw: dict[str, object]) -> DailyCandle:
    # Oanda returns RFC 3339 strings like "2025-05-12T21:00:00.000000000Z"
    time_str = str(raw["time"]).rstrip("Z").split(".")[0]  # trim nanoseconds + Z
    time_utc = datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)

    bid_raw = raw.get("bid")
    ask_raw = raw.get("ask")

    if not isinstance(bid_raw, dict) or not isinstance(ask_raw, dict):
        raise ValueError(f"Missing bid/ask in candle payload: {raw}")

    return DailyCandle(
        time=time_utc,
        bid=_parse_ohlc(bid_raw),
        ask=_parse_ohlc(ask_raw),
        volume=int(str(raw["volume"])),
        complete=bool(raw["complete"]),
    )


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------

def fetch_weekly_daily_candles(
    instrument: str = INSTRUMENT,
    *,
    days_back: int = 7,
) -> list[DailyCandle]:
    """
    Return up to `days_back` daily BA candles for `instrument`.

    Only *complete* candles are returned — the in-progress candle Oanda
    appends by default is silently dropped to prevent look-ahead bias.
    """
    api_token = _require_env("OANDA_API_TOKEN")

    client = oandapyV20.API(access_token=api_token, environment=ENVIRONMENT)

    # Request a window that comfortably covers 7 trading days.
    # We over-fetch slightly and let the `complete` filter trim the tail.
    from_dt = datetime.now(tz=timezone.utc) - timedelta(days=days_back + 3)
    from_str = from_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    params: dict[str, str | int] = {
        "granularity": GRANULARITY,
        "price": PRICE,
        "dailyAlignment": DAILY_ALIGNMENT,
        "alignmentTimezone": ALIGNMENT_TZ,
        "from": from_str,
        "count": days_back + 5,  # small buffer; API max is 5000
    }

    request = v20instruments.InstrumentsCandles(instrument, params=params)
    client.request(request)

    raw_candles: list[dict[str, object]] = request.response.get("candles", [])
    all_candles = [_parse_candle(c) for c in raw_candles]

    complete_only = [c for c in all_candles if c.complete]
    return complete_only[-days_back:]  # keep only the requested window


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _print_candles(candles: list[DailyCandle]) -> None:
    header = (
        f"{'Date (UTC)':>12}  "
        f"{'Bid O':>8} {'Bid H':>8} {'Bid L':>8} {'Bid C':>8}  "
        f"{'Ask O':>8} {'Ask H':>8} {'Ask L':>8} {'Ask C':>8}  "
        f"{'Vol':>8}  {'Complete':>8}"
    )
    separator = "-" * len(header)

    print(f"\nEUR/USD — daily BA candles (17:00 New York close)\n{separator}")
    print(header)
    print(separator)

    # To check if the timestamps end in T21:00:00Z (NY summer) or T22:00:00Z (NY winter)
    # If yes, comment them out.
    for c in candles:
        print(c.time.isoformat())

    for c in candles:
        date_str = c.time.strftime("%Y-%m-%d")
        print(
            f"{date_str:>12}  "
            f"{c.bid.o:>8.5f} {c.bid.h:>8.5f} {c.bid.l:>8.5f} {c.bid.c:>8.5f}  "
            f"{c.ask.o:>8.5f} {c.ask.h:>8.5f} {c.ask.l:>8.5f} {c.ask.c:>8.5f}  "
            f"{c.volume:>8}  {str(c.complete):>8}"
        )

    print(separator)
    print(f"  {len(candles)} complete candles returned.\n")


def _print_spread_summary(candles: list[DailyCandle]) -> None:
    """Print the close spread (ask_c - bid_c) for each day in pips."""
    REASONABLE_LOW = 0.00008
    REASONABLE_HIGH = 0.00025

    spread_header = f"{'Date (UTC)':>12}  {'Spread (pips)':>14}  {'Status':>10}"
    spread_sep = "-" * len(spread_header)

    print(f"EUR/USD — close spread by day (ask_c - bid_c)\n{spread_sep}")
    print(spread_header)
    print(spread_sep)

    for c in candles:
        spread = c.ask.c - c.bid.c
        status = "OK" if REASONABLE_LOW <= spread <= REASONABLE_HIGH else "UNUSUAL"
        date_str = c.time.strftime("%Y-%m-%d")
        print(f"{date_str:>12}  {spread:>14.5f}  {status:>10}")

    print(spread_sep + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    candles = fetch_weekly_daily_candles(days_back=7)
    _print_candles(candles)
    _print_spread_summary(candles)

    # -----------------------------------------------------------------------
    # INSPECTION CHECKLIST — do this manually before writing any more code
    # -----------------------------------------------------------------------
    # 1. Are all `complete` values True?  (The incomplete candle must be gone.)
    # 2. Do the timestamps end in T21:00:00Z (NY summer) or T22:00:00Z (NY winter)?
    #    Any other suffix means your alignment is wrong.
    # 3. Is bid_c < ask_c on every row?  If not, the data is broken.
    # 4. Does the spread (ask_c - bid_c) look reasonable — ~0.00010 to 0.00020
    #    for EURUSD during normal conditions?
    # 
    # Update (2026 Jun. 28th):
    # A for Q1: Yes
    # A for Q2: Yes
    # A for Q3: Yes
    # A for Q4: Yes for most days


if __name__ == "__main__":
    main()