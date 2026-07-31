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

DEFAULT_SMA_PERIOD: Final[int] = 3
DEFAULT_RSI_PERIOD: Final[int] = 14

RANDOM_NUMBERS_UPPER_BOUND: Final[float] = 1.20000
RANDOM_NUMBERS_LOWER_BOUND: Final[float] = 1.10000
NUMBER_OF_RANDOM_NUMBERS: Final[int] = 100
DEFAULT_RANDOM_NUMBERS_DECIMALS: Final[int] = 5


def generate_fake_fx_data(
    lower_bound: float = RANDOM_NUMBERS_LOWER_BOUND,
    upper_bound: float = RANDOM_NUMBERS_UPPER_BOUND,
    count: int = NUMBER_OF_RANDOM_NUMBERS,
    decimals: int = DEFAULT_RANDOM_NUMBERS_DECIMALS,
) -> pd.DataFrame:
    """Generate a DataFrame of fake FX closing rates for local testing.

    Draws ``count`` values uniformly at random from the open interval
    ``(lower_bound, upper_bound)`` and rounds them to ``decimals`` places.
    Rounding alone can push a value exactly onto ``lower_bound`` or
    ``upper_bound``; the result is then clipped one unit-in-the-last-place
    inward on each side so every value stays strictly inside the bounds.

    Args:
        lower_bound: Exclusive lower bound of the generated rates.
        upper_bound: Exclusive upper bound of the generated rates.
        count: Number of rates to generate. Must be a positive integer.
        decimals: Number of decimal places to round each rate to.

    Returns:
        A ``pandas.DataFrame`` with a single ``"rate"`` column of length
        ``count``.

    Raises:
        ValueError: If ``count`` is not a positive integer.
    """
    if count <= 0:
        raise ValueError(f"count must be a positive integer, got {count}")

    epsilon = 10 ** -decimals
    rng = np.random.default_rng()
    raw_random_values = (
        rng.uniform(low=lower_bound, high=upper_bound, size=count)
        .round(decimals=decimals)
    )
    random_values = np.clip(
        a=raw_random_values,
        a_min=lower_bound + epsilon,
        a_max=upper_bound - epsilon,
    )
    return pd.DataFrame({"rate": random_values})


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

    fake_fx_data = generate_fake_fx_data()

    # line = sma(sample, period=DEFAULT_SMA_PERIOD)
    # line = sma_in_pandas(sample, period=DEFAULT_SMA_PERIOD)
    # print(line)  # [None, None, 2.0, 3.0, 4.0]
    print(fake_fx_data)
    output = talib.RSI(
        real=fake_fx_data["rate"].to_numpy(),
        timeperiod=DEFAULT_RSI_PERIOD
    )
    fake_fx_data["RSI_14"] = output
    print(output)
    print(fake_fx_data)
