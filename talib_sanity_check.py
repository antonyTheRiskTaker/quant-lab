import numpy as np
import talib

def main():
    print(f"Wrapper: {talib.__version__} | C lib: {talib.__ta_version__.decode().strip()}")
    print(f"Functions available: {len(talib.get_functions())}")

    # fake daily closes just to confirm the math runs
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 1, 100))
    sma = talib.SMA(close, timeperiod=20)
    rsi = talib.RSI(close, timeperiod=14)
    macd, sig, hist = talib.MACD(close, 12, 26, 9)
    print(f"Close {close[-1]:.2f} | SMA20 {sma[-1]:.2f} | RSI14 {rsi[-1]:.2f} | MACD hist {hist[-1]:.4f}")


if __name__ == "__main__":
    main()