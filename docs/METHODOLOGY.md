# 07  Indicator definitions and warm-up

| Output | Definition / convention | First usable bar |
| --- | --- | --- |
| sma20 / sma50 | Arithmetic mean of last 20 / 50 closes | 20 / 50 |
| rsi14 | TA-Lib Wilder RSI, period 14 | 15 |
| macd / signal / histogram | TA-Lib EMA parameters 12,26,9; histogram = MACD - signal | 34 |
| bb_upper/middle/lower | SMA20 +/- 2 population standard deviations | 20 |
| atr14 | TA-Lib Wilder true-range average, period 14 | 15 |
| daily_return / return20 | close / previous close - 1; close / close 20 days earlier - 1 | 2 / 21 |
| volatility20 | Sample std of 20 daily returns x sqrt(365) | 21 |
| volume_ratio | Current volume / mean of previous 20 volumes | 21 |

The bar number counts from one. Warm-up values are JSON null, never zero substitutes. SMA trend remains unavailable until SMA50 exists; then it is up, down or flat according to SMA20 versus SMA50. A moving-average cross requires both the current and preceding values to be available.

TA-Lib owns RSI, MACD and ATR initialization and smoothing conventions. Flat RSI is zero under the tested pinned implementation; this is not an estimate of "zero market risk." A zero volume baseline makes volume_ratio null, even when current volume is positive, because division by zero has no defined ratio.

Market-specific holidays are not supported: these daily crypto series expect consecutive calendar days. Equity and factory business-day datasets need a different calendar contract and annualization choice.

# 08  Calculation examples and units

## Moving average and daily return

With 20 closes 100, 101, ..., 119, SMA20 is (100 + 119) / 2 = 109.5. If yesterday closes at 100 and today at 102, daily_return = 102 / 100 - 1 = 0.02, meaning 2%. Reports retain ratios as fractions rather than already formatted percentages.

## Volume surprise

If each preceding 20 bars has volume 100 and today has volume 1,000, baseline20 = 100 and volume_ratio = 10. The current bar is excluded from the baseline. Including it would weaken the spike signal by raising its own comparison baseline. A configured ratio limit of 2 triggers an alert when the ratio is strictly greater than 2.

## Historical volatility

```python
# Actual implementation in indicators.py
returns = np.full(len(close), np.nan)
returns[1:] = close[1:] / close[:-1] - 1
vol = (
    float(np.std(returns[i-19:i+1], ddof=1) * math.sqrt(365))
    if i >= 20 else None
)
```

The 20 returns ending on the chosen bar use 21 closing prices. ddof=1 selects sample standard deviation. The square-root annualization uses 365 because crypto trades every day. volatility20 = 0.80 means 80% annualized historical volatility; it is neither a future forecast nor a maximum possible loss.

Open, high and low affect ATR; close drives moving averages, RSI, MACD and Bollinger Bands. Validation keeps inputs finite. The regime model also rejects extreme feature ranges rather than forcing unstable clustering. Serialized outputs are checked with allow_nan=False before the analysis is committed.

# 09  Programming the indicator engine

```python
# Actual calls from indicators.py
sma20 = talib.SMA(close, 20)
sma50 = talib.SMA(close, 50)
rsi = talib.RSI(close, 14)
atr = talib.ATR(high, low, close, 14)
macd, signal, hist = talib.MACD(close, 12, 26, 9)
upper, middle, lower = talib.BBANDS(close, 20, 2, 2, 0)

def finite(value):
    return float(value) if np.isfinite(value) else None
```

calculate() converts validated decimal-string candle values into NumPy float64 arrays, invokes TA-Lib and builds one history row per candle. finite() converts warm-up NaN values into JSON null. The original decimal strings remain in the saved input snapshot while analytical results use floating-point values.

## Analysis orchestration in engine.py

evaluate() first checks as_of against coverage_end. It selects requested market IDs, excludes all later candles and requires an exact as_of bar for each selected market. This prevents the report from quietly presenting a stale close as the current market value. Unknown markets and missing analysis-date bars return 422.

The function computes each market history, runs optional clustering, attaches later regime labels and generates alert evidence. It returns latest summaries, complete histories, alerts, methodology and library versions. These values are saved together with thresholds and source data by the routes/storage layer.

## Development plan for this module

Build pure functions before HTTP integration. Test arithmetic SMA and Bollinger values, Wilder RSI, flat ATR, MACD identity and first usable bars. Add selection and no-future-data tests. Only then wire the engine into a transaction that creates immutable analyses.

# 10  Explainable alert design

| Code | Trigger | Evidence |
| --- | --- | --- |
| SMA_CROSS_UP / DOWN | SMA20-SMA50 changes side with ready previous values | Before/after difference |
| MACD_CROSS_UP / DOWN | MACD-signal changes side with ready previous values | Before/after difference |
| RSI_HIGH_ENTRY | Previous RSI < high; current RSI >= high | RSI and threshold |
| RSI_LOW_ENTRY | Previous RSI > low; current RSI <= low | RSI and threshold |
| VOLUME_SPIKE | Current/past-20 volume > configured limit | Ratio and limit |
| LARGE_DAILY_MOVE | Absolute daily return > configured limit | Signed return and limit |
| HIGH_HISTORICAL_VOLATILITY | Annualized volatility20 > configured limit | Historical volatility and limit |

Crosses and RSI entries are transition events; the API does not repeat them every day merely because a level remains high. Volume, return and volatility alerts are daily conditions and can repeat on consecutive bars. Report history includes all alerts through as_of, not just the latest day.

Every alert includes date, market_id, code, a plain explanation and numeric evidence. Thresholds are saved in inputs. Defaults are RSI 30/70, volume ratio 2, absolute daily move 0.10 and annualized historical volatility 0.80. These are configurable product defaults, not recommendations for a particular investor.

An alert explains a numerical event. It does not imply buy/sell profitability or an expected reversal. Notification scheduling, persistence acknowledgement and deduplicated message delivery are future modules; the current service returns and exports alerts only.

# 11  Optional AI: market regimes

The implemented AI is unsupervised clustering. It groups historical feature rows into three conditions relative to the same market. It does not learn a future price target, probability of profit or a directional trading strategy.

| Step | Implemented behavior |
| --- | --- |
| Feature construction | SMA20/SMA50 - 1; historical volatility20; ATR14/close |
| Warm-up | First complete features occur on bar 50 |
| Training baseline | First 60 complete feature rows only |
| Scaling | StandardScaler fits only the training baseline |
| Model | KMeans: 3 clusters, random_state=42, n_init=10 |
| Classification | Only later rows; at least 10 are required |
| Minimum history | 119 bars = 49 warm-up + 60 training + 10 scoring |
| Labels | Cluster centers sorted by trend gap: relatively lower / middle / relatively higher trend |

This temporal design lets the API classify later conditions using a fixed earlier reference. Extending a dataset with future candles does not change the existing training centers or earlier predictions when the historical prefix is unchanged. Retraining is not implemented.

Labels are relative to the market baseline. "Relatively higher trend" can still be negative in absolute terms if all baseline clusters have negative trend gaps. Comparing labels across different markets is not an equivalent statistical comparison. No confidence probability is attached to a cluster assignment.

# 12  Programming and evaluating the model

```python
# Actual training block in regimes.py
train = features[:60]
if len(np.unique(train, axis=0)) < 3:
    return dict(status="degenerate_training_data",
                parameters=metadata, predictions=[])
scaler = StandardScaler().fit(train)
with threadpool_limits(limits=1):
    model = KMeans(n_clusters=3, n_init=10,
                   random_state=42).fit(scaler.transform(train))
    labels = model.predict(scaler.transform(features[60:]))
centers = scaler.inverse_transform(model.cluster_centers_)
```

Scaling balances feature magnitudes. Fitting the scaler on all rows would allow future distributions to influence the training baseline. The code deliberately fits on train only. threadpool_limits(1) bounds numerical-library threads for this small local workload.

| Status | Interpretation |
| --- | --- |
| available | At least 60 complete training and 10 later scoring rows exist |
| disabled | The caller set enable_ml=false |
| insufficient_history | Indicators still work, but clustering lacks enough rows |
| degenerate_training_data | Fewer than three distinct training feature rows |
| unsupported_numeric_range | Non-finite or extreme features; clustering is skipped |

The verification checks repeatability and chronology, not model usefulness or investment performance. Before presenting a forecasting product, define a future target, use walk-forward splits, compare a simple baseline, quantify uncertainty and evaluate out-of-sample errors. That would be a new supervised module rather than a marketing claim about this clustering model.
