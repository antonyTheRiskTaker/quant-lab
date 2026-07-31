"""Simple Moving Average (SMA) — a first NNFX-style baseline indicator.

Design notes
------------
* Signals are computed on the MID price. You deliberately stored bid AND ask,
  but the spread is an EXECUTION cost, not a signal input: compute the SMA on
  mid, then charge the spread when you simulate the fill. ``mid()`` is provided
  for exactly that.
* The output is aligned to the input by index. The first ``period - 1`` slots
  are ``None`` because there is not yet a full window. Equal length means you
  can zip indicator values straight back onto candles with no off-by-one bugs.
"""

from collections.abc import Sequence
from statistics import fmean
from typing import Final

import pandas as pd
import numpy as np
import talib

DEFAULT_BASELINE_PERIOD: Final[int] = 3


def mid(bid: float, ask: float) -> float:
    """Midpoint of a bid/ask pair. Use for signals; pay the spread on the fill."""
    return (bid + ask) / 2.0


def sma(values: Sequence[float], period: int) -> list[float | None]:
    """Simple moving average of ``values``, output aligned to the input length.

    The value at index ``i`` is the arithmetic mean of the ``period`` values
    ending at ``i``. Any index with fewer than ``period`` preceding values is
    ``None``.

    Args:
        values: The price series (e.g. mid closes), oldest first.
        period: The lookback window length. Must be a positive integer.

    Returns:
        A list the same length as ``values``.

    Raises:
        ValueError: If ``period`` is not a positive integer.
    """
    if period <= 0:
        raise ValueError(f"period must be a positive integer, got {period}")

    result: list[float | None] = []
    for index in range(len(values)):
        if index + 1 < period:
            result.append(None)
            continue
        window = values[index + 1 - period : index + 1]
        result.append(fmean(window))
    return result


def sma_in_pandas(values: Sequence[float], period: int) -> pd.Series:
    """Simple moving average of ``values``, computed with pandas.

    A pandas-based sibling of :func:`sma`, kept separate so the two
    implementations can be compared directly. Unlike ``sma()``, the result
    is a native ``pandas.Series`` and incomplete windows are ``NaN``
    rather than ``None`` (pandas' convention, not Python's).

    Args:
        values: The price series (e.g. mid closes), oldest first.
        period: The lookback window length. Must be a positive integer.

    Returns:
        A ``pandas.Series`` the same length as ``values``.

    Raises:
        ValueError: If ``period`` is not a positive integer.
    """
    if period <= 0:
        raise ValueError(f"period must be a positive integer, got {period}")

    series = pd.Series(values, dtype=float)
    return series.rolling(window=period).mean()


if __name__ == "__main__":
    sample: list[float] = [1.0, 2.0, 3.0, 4.0, 5.0]
    # line = sma(sample, period=DEFAULT_BASELINE_PERIOD)
    line = sma_in_pandas(sample, period=DEFAULT_BASELINE_PERIOD)
    print(line)  # [None, None, 2.0, 3.0, 4.0]