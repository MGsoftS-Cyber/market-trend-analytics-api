"""Pure analytical evaluation from a saved input snapshot."""

from collections import defaultdict
from importlib.metadata import version
from .indicators import calculate
from .regimes import classify

ENGINE_VERSION = "trend-1.0.0"


def evaluate(inputs):
    as_of = inputs["as_of"]
    if as_of > inputs["coverage_end"]:
        raise ValueError("as_of is later than dataset coverage_end.")
    groups = defaultdict(list)
    for bar in inputs["candles"]:
        groups[bar["market_id"]].append(bar)
    selected = inputs.get("market_ids") or sorted(groups)
    if any(k not in groups for k in selected):
        raise ValueError("An analysis market is absent from the dataset.")
    markets = []
    all_history = []
    alerts = []
    for market in selected:
        bars = sorted([b for b in groups[market] if b["date"] <= as_of], key=lambda b: b["date"])
        if not bars or bars[-1]["date"] != as_of:
            raise ValueError(f"{market}: requires an exact completed candle on as_of.")
        history = calculate(bars)
        ml = classify(history, inputs["enable_ml"])
        predictions = {x["date"]: x for x in ml["predictions"]}
        for i, row in enumerate(history):
            row["regime"] = predictions.get(row["date"], {}).get("regime")
            prev = history[i - 1] if i else None

            def emit(code, message, evidence):
                alerts.append(dict(date=row["date"], market_id=market, code=code, message=message, evidence=evidence))

            for field, reference, code in [("sma20", "sma50", "SMA_CROSS"), ("macd", "macd_signal", "MACD_CROSS")]:
                if prev and all(x[k] is not None for x in [prev, row] for k in [field, reference]):
                    before = prev[field] - prev[reference]
                    after = row[field] - row[reference]
                    if before <= 0 < after or before >= 0 > after:
                        emit(
                            code + ("_UP" if after > 0 else "_DOWN"),
                            f"{field} crossed {reference}.",
                            dict(before=before, after=after),
                        )
            if prev and prev["rsi14"] is not None and row["rsi14"] is not None:
                if prev["rsi14"] < inputs["rsi_high"] <= row["rsi14"]:
                    emit(
                        "RSI_HIGH_ENTRY",
                        "RSI entered the configured high zone.",
                        dict(rsi14=row["rsi14"], threshold=inputs["rsi_high"]),
                    )
                if prev["rsi14"] > inputs["rsi_low"] >= row["rsi14"]:
                    emit(
                        "RSI_LOW_ENTRY",
                        "RSI entered the configured low zone.",
                        dict(rsi14=row["rsi14"], threshold=inputs["rsi_low"]),
                    )
            for field, limit, code, absolute in [
                ("volume_ratio", "volume_ratio_limit", "VOLUME_SPIKE", False),
                ("daily_return", "daily_change_limit", "LARGE_DAILY_MOVE", True),
                ("volatility20", "volatility_limit", "HIGH_HISTORICAL_VOLATILITY", False),
            ]:
                value = row[field]
                if value is not None and (abs(value) if absolute else value) > inputs[limit]:
                    emit(
                        code, f"{field} exceeded its configured threshold.", dict(value=value, threshold=inputs[limit])
                    )
        latest = history[-1].copy()
        markets.append(
            dict(
                market_id=market,
                bars_used=len(bars),
                latest=latest,
                model=ml,
                warnings=[
                    "Unavailable indicators remain null during warm-up.",
                    "Indicators describe historical data; no execution or price prediction.",
                ],
            )
        )
        all_history.extend(history)
    return dict(
        engine_version=ENGINE_VERSION,
        as_of=as_of,
        markets=markets,
        history=all_history,
        alerts=alerts,
        libraries={k: version(k) for k in ["numpy", "TA-Lib", "scikit-learn"]},
        methodology=dict(
            timeframe="1d",
            timezone="UTC",
            quote_currency="USD",
            annualization_days=365,
            volatility_window=20,
            volatility_ddof=1,
            volume_baseline="previous 20 completed bars excluding current",
            macd=[12, 26, 9],
            rsi_period=14,
            bollinger=[20, 2, 2],
            atr_period=14,
        ),
        limitations=[
            "No corporate-action adjustment, intraday analysis, trading, order routing, or investment advice.",
            "Clustering is descriptive; no predictive accuracy claim or calibrated confidence.",
        ],
    )
