"""
Oanda v20 API fetcher — generalised for any instrument and date range,
with transparent pagination.

WHY PAGINATION IS NECESSARY
----------------------------
The Oanda API returns at most 5 000 candles per request.
EUR/USD history on Oanda begins around 2003 — that is ~5 800 daily candles.
Without pagination the oldest ~800 candles would be silently lost.
fetch_all_daily_candles() handles this automatically.

CREDENTIALS
-----------
Never hard-code these.  Set them in your shell or .env file:

    OANDA_API_TOKEN   — your Oanda v20 personal access token
    OANDA_ACCOUNT_ID  — your Oanda account ID  (e.g. "101-004-XXXXXXX-001")

TYPE IGNORE COMMENTS
--------------------
oandapyV20 ships with no type stubs.  Every # type: ignore[...] below is
an explicit, documented suppression — not laziness.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Final

import oandapyV20  # type: ignore[import-untyped]
import oandapyV20.endpoints.instruments as v20instruments  # type: ignore[import-untyped]

from models import DailyCandle, OhlcHalf

# ---------------------------------------------------------------------------
# Constants  (established in sessions 1 & 2 — do not change without reason)
# ---------------------------------------------------------------------------

GRANULARITY: Final[str] = "D"
PRICE: Final[str] = "BA"            # bid AND ask — never mid
DAILY_ALIGNMENT: Final[int] = 17    # 17:00 New York — global FX close convention
ALIGNMENT_TZ: Final[str] = "America/New_York"
ENVIRONMENT: Final[str] = "practice"  # change to "live" only when ready

# Hard limit imposed by the Oanda API.  Never raise this.
_API_PAGE_SIZE: Final[int] = 5_000


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{name}' is not set. "
            "Add it to your shell profile or .env file — never hard-code credentials."
        )
    return value


def _extract_dict(val: object, field_name: str) -> dict[str, object]:
    """Narrow `val` to dict; raise a clear error if the API shape has changed."""
    if not isinstance(val, dict):
        raise ValueError(
            f"Expected a dict for field '{field_name}', "
            f"got {type(val).__name__}. "
            "Oanda API response shape may have changed."
        )
    return val  # type: ignore[return-value]


def _parse_ohlc(raw: dict[str, object]) -> OhlcHalf:
    return OhlcHalf(
        o=float(str(raw["o"])),
        h=float(str(raw["h"])),
        l=float(str(raw["l"])),
        c=float(str(raw["c"])),
    )


def _parse_candle(raw: dict[str, object]) -> DailyCandle:
    # Oanda returns RFC 3339: "2026-05-19T21:00:00.000000000Z"
    # Strip nanoseconds and trailing Z before fromisoformat.
    time_str = str(raw["time"]).rstrip("Z").split(".")[0]
    time_utc = datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)

    bid_raw = _extract_dict(raw.get("bid"), "bid")
    ask_raw = _extract_dict(raw.get("ask"), "ask")

    return DailyCandle(
        time=time_utc,
        bid=_parse_ohlc(bid_raw),
        ask=_parse_ohlc(ask_raw),
        volume=int(str(raw["volume"])),
        complete=bool(raw["complete"]),
    )


def _fetch_one_page(
    client: oandapyV20.API,  # type: ignore[name-defined]
    instrument: str,
    from_dt: datetime,
) -> list[DailyCandle]:
    """
    Fetch one page (up to _API_PAGE_SIZE candles) starting from `from_dt`.
    Returns only complete candles.
    """
    params: dict[str, str | int] = {
        "granularity": GRANULARITY,
        "price": PRICE,
        "dailyAlignment": DAILY_ALIGNMENT,
        "alignmentTimezone": ALIGNMENT_TZ,
        "from": from_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": _API_PAGE_SIZE,
    }

    request = v20instruments.InstrumentsCandles(instrument, params=params)
    client.request(request)  # type: ignore[no-untyped-call]

    response: dict[str, object] = request.response  # type: ignore[attr-defined]
    raw_list = response.get("candles", [])

    if not isinstance(raw_list, list):
        raise ValueError(
            f"Unexpected API response for {instrument}: "
            f"'candles' field is not a list."
        )

    all_candles = [_parse_candle(c) for c in raw_list if isinstance(c, dict)]
    return [c for c in all_candles if c.complete]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_all_daily_candles(
    instrument: str,
    *,
    from_dt: datetime,
) -> list[DailyCandle]:
    """
    Fetch ALL available daily BA candles for `instrument` from `from_dt`
    to the most recently completed candle.

    Pagination is handled transparently: the function keeps requesting the
    next page until Oanda returns fewer than _API_PAGE_SIZE candles (meaning
    there is no more data).

    Only complete candles are returned.  The in-progress candle that Oanda
    always appends is dropped to prevent look-ahead bias.

    Parameters
    ----------
    instrument:
        Oanda instrument code, e.g. "EUR_USD", "USD_JPY".
    from_dt:
        Inclusive start datetime (UTC, timezone-aware).

    Raises
    ------
    EnvironmentError  — OANDA_API_TOKEN is not set.
    ValueError        — unexpected API response shape.
    oandapyV20.exceptions.V20Error — non-200 response from Oanda.
    """
    api_token = _require_env("OANDA_API_TOKEN")
    client = oandapyV20.API(access_token=api_token, environment=ENVIRONMENT)

    all_candles: list[DailyCandle] = []
    page_start = from_dt

    while True:
        page = _fetch_one_page(client, instrument, page_start)
        all_candles.extend(page)

        # If the page was not full, we have reached the end of available data.
        if len(page) < _API_PAGE_SIZE:
            break

        # Advance the window to just after the last candle on this page.
        page_start = page[-1].time + timedelta(seconds=1)

    return all_candles