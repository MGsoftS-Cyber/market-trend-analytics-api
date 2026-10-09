"""Historical clustering, not a return forecast or trading recommendation."""

import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

FEATURES = ["sma20/sma50 - 1", "volatility20", "atr14/close"]


def classify(history, enabled):
    metadata = dict(features=FEATURES, training_rows=60, clusters=3, random_state=42, n_init=10)
    if not enabled:
        return dict(status="disabled", method="KMeans", parameters=metadata, predictions=[])
    eligible = [x for x in history if all(x[k] is not None for k in ["sma20", "sma50", "volatility20", "atr14"])]
    if len(eligible) < 70:
        return dict(
            status="insufficient_history",
            reason="Need at least 119 daily candles: 49 warm-up, 60 training, 10 later scoring.",
            parameters=metadata,
            predictions=[],
        )
    features = np.array([[x["sma20"] / x["sma50"] - 1, x["volatility20"], x["atr14"] / x["close"]] for x in eligible])
    if not np.isfinite(features).all() or np.max(np.abs(features)) > 1e6:
        return dict(status="unsupported_numeric_range", parameters=metadata, predictions=[])
    train = features[:60]
    if len(np.unique(train, axis=0)) < 3:
        return dict(status="degenerate_training_data", parameters=metadata, predictions=[])
    scaler = StandardScaler().fit(train)
    with threadpool_limits(limits=1):
        model = KMeans(n_clusters=3, n_init=10, random_state=42).fit(scaler.transform(train))
        labels = model.predict(scaler.transform(features[60:]))
    centers = scaler.inverse_transform(model.cluster_centers_)
    ordered = np.argsort(centers[:, 0])
    names = {int(k): v for k, v in zip(ordered, ["relatively lower trend", "middle trend", "relatively higher trend"])}
    predictions = [
        dict(date=row["date"], regime=names[int(k)], cluster_id=int(k)) for row, k in zip(eligible[60:], labels)
    ]
    return dict(
        status="available",
        method="KMeans",
        parameters=metadata,
        training_start=eligible[0]["date"],
        training_end=eligible[59]["date"],
        scoring_start=eligible[60]["date"],
        centers=[
            dict(cluster_id=i, label=names[i], trend_gap=float(c[0]), volatility20=float(c[1]), atr_ratio=float(c[2]))
            for i, c in enumerate(centers)
        ],
        predictions=predictions,
        interpretation="Relative to this market's fixed training baseline. Labels are not probabilities and do not predict returns.",
    )
