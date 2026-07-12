"""Run the SMA indicator on real data pulled from fx_candles.db.

A verification script: it reads the stored bid/ask closes for one instrument,
converts them to mid prices, runs the SMA, and prints the tail so you can eyeball
the moving average against the raw closes.

The DB read lives here for now. Once we build the strategy layer, the clean home
for a `fetch_*` helper is db.py.
"""

import sqlite3
from dataclasses import dataclass
from typing import Final

from indicators import DEFAULT_BASELINE_PERIOD, mid, sma, sma_in_pandas

DB_PATH: Final[str] = "fx_candles.db"
TABLE: Final[str] = "candles_D"
INSTRUMENT: Final[str] = "EUR_USD"  # Oanda uses an underscore, not "EUR/USD"

# `slots=True` saves memory and speeds up attribute access, a Python 3.10+ feature.
@dataclass(frozen=True, slots=True)
class ClosePoint:
    """One completed daily candle reduced to its mid close."""

    time: str
    mid_close: float


def load_mid_closes(db_path: str, instrument: str) -> list[ClosePoint]:
    """Load completed daily candles for `instrument` as mid closes, oldest first.

    The `ORDER BY time ASC` is not optional: a moving average is meaningless if
    the rows are not in chronological order.
    """
    query = (
        f"SELECT time, bid_c, ask_c FROM {TABLE} "
        "WHERE instrument = ? AND complete = 1 "
        "ORDER BY time ASC"
    )
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query, (instrument,)).fetchall()

    points: list[ClosePoint] = []
    for row in rows:
        time_str = str(row[0])
        mid_close = mid(float(row[1]), float(row[2]))
        points.append(ClosePoint(time=time_str, mid_close=mid_close))
    return points


def distinct_instruments(db_path: str) -> list[str]:
    """List the instrument codes actually present (for diagnostics)."""
    query = f"SELECT DISTINCT instrument FROM {TABLE} ORDER BY instrument"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query).fetchall()
    return [str(row[0]) for row in rows]


def raw_row_count(db_path: str, instrument: str) -> int:
    """Count rows for an instrument ignoring the `complete` filter."""
    query = f"SELECT COUNT(*) FROM {TABLE} WHERE instrument = ?"
    with sqlite3.connect(db_path) as conn:
        result = conn.execute(query, (instrument,)).fetchone()
    return int(result[0]) if result is not None else 0


def report_empty(db_path: str, instrument: str) -> None:
    """Explain *why* a load came back empty instead of failing silently."""
    raw = raw_row_count(db_path, instrument)
    print(f"No completed candles found for {instrument!r}.")
    if raw > 0:
        print(f"  {raw} rows exist but none passed complete = 1 "
              "— check how 'complete' was stored.")
    else:
        print(f"  No rows at all for {instrument!r} — likely the wrong code.")
    print(f"  Instruments actually stored: {distinct_instruments(db_path)}")


def main() -> None:
    points = load_mid_closes(DB_PATH, INSTRUMENT)
    if not points:
        report_empty(DB_PATH, INSTRUMENT)
        return

    closes: list[float] = [point.mid_close for point in points]
    line = sma(closes, period=DEFAULT_BASELINE_PERIOD)
    # line = sma_in_pandas(closes, period=DEFAULT_BASELINE_PERIOD)
    # print(line)

    print(f"{INSTRUMENT}: {len(points)} completed daily candles")
    print(f"SMA period: {DEFAULT_BASELINE_PERIOD}\n")
    print(f"{'time':30} {'mid_close':>11} {'sma':>11}")
    for point, sma_value in list(zip(points, line, strict=True))[-10:]:
        sma_text = "—" if sma_value is None else f"{sma_value:.5f}"
        print(f"{point.time:30} {point.mid_close:>11.5f} {sma_text:>11}")

if __name__ == "__main__":
    main()