"""TA-Lib indicators retain their native warm-up conventions (null in JSON)."""

import math
import numpy as np
import talib


def finite(value):
    return float(value) if np.isfinite(value) else None


def calculate(bars):
    close = np.array([float(x["close"]) for x in bars], dtype="float64")
    high = np.array([float(x["high"]) for x in bars], dtype="float64")
    low = np.array([float(x["low"]) for x in bars], dtype="float64")
    volume = np.array([float(x["volume"]) for x in bars], dtype="float64")
    sma20 = talib.SMA(close, 20)
    sma50 = talib.SMA(close, 50)
    rsi = talib.RSI(close, 14)
    atr = talib.ATR(high, low, close, 14)
    macd, signal, hist = talib.MACD(close, 12, 26, 9)
    upper, middle, lower = talib.BBANDS(close, 20, 2, 2, 0)
    returns = np.full(len(close), np.nan)
    returns[1:] = close[1:] / close[:-1] - 1
    output = []
    for i, b in enumerate(bars):
        baseline = float(np.mean(volume[i - 20 : i])) if i >= 20 else None
        vol = float(np.std(returns[i - 19 : i + 1], ddof=1) * math.sqrt(365)) if i >= 20 else None
        output.append(
            dict(
                date=b["date"],
                market_id=b["market_id"],
                close=float(close[i]),
                volume=float(volume[i]),
                sma20=finite(sma20[i]),
                sma50=finite(sma50[i]),
                rsi14=finite(rsi[i]),
                atr14=finite(atr[i]),
                macd=finite(macd[i]),
                macd_signal=finite(signal[i]),
                macd_histogram=finite(hist[i]),
                bb_upper=finite(upper[i]),
                bb_middle=finite(middle[i]),
                bb_lower=finite(lower[i]),
                daily_return=finite(returns[i]),
                return20=float(close[i] / close[i - 20] - 1) if i >= 20 else None,
                volatility20=vol,
                volume_baseline20=baseline,
                volume_ratio=float(volume[i] / baseline) if baseline is not None and baseline > 0 else None,
                trend="unavailable"
                if i < 49
                else ("up" if sma20[i] > sma50[i] else "down" if sma20[i] < sma50[i] else "flat"),
            )
        )
    return output
