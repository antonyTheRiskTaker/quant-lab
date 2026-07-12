"""
Shared data models for FX candle data.

These are the canonical types used across the entire project.
Frozen dataclasses = immutable after creation, safe to cache and hash.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OhlcHalf:
    """OHLC values for one side of the spread (bid OR ask)."""

    o: float
    h: float
    l: float  # noqa: E741  — 'l' is conventional in OHLC
    c: float


@dataclass(frozen=True)
class DailyCandle:
    """One complete daily BA (bid + ask) candle from the Oanda API."""

    time: datetime  # UTC, timezone-aware; this is the candle OPEN time (= prior close)
    bid: OhlcHalf
    ask: OhlcHalf
    volume: int
    complete: bool  # always True for candles stored in the DB