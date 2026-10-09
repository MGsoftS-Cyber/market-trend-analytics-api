# Market Trend Analytics API

Conception, programming guide and module-by-module development plan. A runnable Python API for completed daily crypto spot candles, with explainable technical indicators and optional machine learning.

| Deliverable | Included |
| --- | --- |
| API project | FastAPI, authentication, datasets, analysis, exports and Swagger |
| Analytics | SMA, RSI, MACD, Bollinger Bands, ATR, volume and volatility |
| Optional AI | KMeans regime clustering using earlier training data |
| Operation | Local SQLite or supplied Docker/PostgreSQL setup |
| Evidence | 43 passing tests and a complete real HTTP smoke run |

The implementation operates without a paid AI service, cloud server, wallet connection or exchange credential. The included example data is synthetic. This release imports CSV/JSON; live exchange feeds and a custom dashboard are planned extensions.

## How to use this guide

Read pages 2-6 for product and data design, pages 7-13 for calculations and coding, pages 14-18 for API integration and operation, and pages 19-22 for verification, implementation planning and references. The ZIP contains editable source and matching Markdown documentation.

# 01  Product conception

The central question is: "What do recent price and volume movements tell us about the current market condition?" The API gives a reproducible historical answer for each chosen market, rather than generating an unverified trading instruction.

## Primary users and workflows

| User | Workflow | Result |
| --- | --- | --- |
| Crypto analyst | Import a completed daily export; choose an analysis date | Indicators, historical alerts and relative regime |
| Finance manager | Monitor volatility and unusually large moves | Threshold evidence with dates and values |
| Developer / ERP team | Call an owner-scoped API from another application | Saved JSON/CSV reports and OpenAPI contracts |

An account owns named workspaces. Each workspace holds immutable datasets. An analysis chooses a dataset, date, markets, thresholds and whether to run clustering. The report preserves both the full input snapshot and computed results, so a later upload cannot silently alter an old report.

## Scope of the first release

USD-quoted crypto spot pairs; one declared venue per dataset; UTC daily bars; base-asset volume. Upload up to 20 markets and 730 bars per market. A current-day bar is rejected because its daily close is not complete. The service does not place orders or connect wallets.

Success means validated imports, numerically checked indicators, useful null values during warm-up, no future-data leakage in the model, owner-only report access and repeatable saved outputs. Profitability or predictive accuracy is not claimed.

# 02  Application architecture

Architecture: client -> FastAPI -> SQLAlchemy/storage; frozen-input engine -> TA-Lib/NumPy and optional scikit-learn.

FastAPI handles HTTP, request contracts and authentication. SQLAlchemy stores owner-scoped records. Pure analytical modules receive dictionaries of validated historical candles and return JSON-safe results; they do not open sockets or execute trades.

| Layer | Files | Responsibility |
| --- | --- | --- |
| Boundary | main.py, schemas.py, routes.py | Sessions, typed contracts and HTTP orchestration |
| Data / storage | imports.py, models.py, services.py | Validation, ownership and atomic replay receipts |
| Analytics | indicators.py, engine.py, regimes.py | Technical values, explained alerts and clustering |

The initial API computes synchronously. Maximum data limits keep the workflow bounded, but many simultaneous users can still consume CPU and memory. Before public scale, move analysis to a queue, cap request bodies at the reverse proxy and introduce shared throttling and retention controls.

# 03  Data model and ownership

Data model: User owns LoginSession, Workspace and RequestRecord. Workspace owns Dataset and Analysis; Analysis references Dataset.

| Record | Key information |
| --- | --- |
| User / session | Argon2 hash; opaque token digest, expiry and CSRF token |
| Workspace | User foreign key; unique name per account; USD quote |
| Dataset | Workspace foreign key; canonical candle JSON, source, venue, coverage, quality, fingerprint |
| Analysis | Workspace/dataset foreign keys; immutable input/result JSON, engine version and creation time |
| RequestRecord | Unique user + scope + key; payload hash and saved response |

All fetches and exports check ownership through Workspace.user_id. A foreign report identifier returns 404. There are no update/delete routes for datasets or reports. These application semantics are immutable; administrators with database access could still modify storage, so production auditing is a separate concern.

# 04  Languages, libraries and cost

| Technology | Why it is used | Version |
| --- | --- | --- |
| Python / FastAPI | Readable analysis code; HTTP endpoints; generated OpenAPI | 3.12 / 0.142.2 |
| Pydantic | Typed fields, decimal inputs and bounded contracts | 2.13.5 |
| TA-Lib / NumPy | Native technical indicators and array calculations | 0.8.1 / 2.5.3 |
| scikit-learn | StandardScaler and deterministic KMeans clustering | 1.9.1 |
| SQLAlchemy / Alembic | Database models and versioned schema migrations | 2.1.3 / 1.20.0 |
| Argon2 / HTTPX | Password hashing and real API client | 25.1.0 / 0.28.1 |
| SQLite / PostgreSQL | Local database / supplied container database | SQLite runtime / PostgreSQL 17 |

No subscription is required by the implemented workflow. The Python libraries are open source, subject to their individual licenses. The source project uses MIT. Hosting, managed databases and commercial data feeds may introduce separate costs; free software does not make infrastructure or proprietary market data free.

## Paid options and AI choices

A future paid market-data connector can supply a licensed candle history. A hosted language model could summarize verified alert evidence, but would add usage charges and must never invent numerical values. Neither dependency is required or implemented here. The current optional AI runs locally and classifies historical conditions using KMeans.

Use the complete requirements.lock.txt for reproducible installs. TA-Lib binary wheels were installed successfully in this environment. Other operating systems or architectures may need the upstream C library when no compatible wheel is available.

# 05  Candle contracts and quality

| Field / rule | Meaning |
| --- | --- |
| date / market_id | Completed UTC date; stable lowercase ID such as bitcoin-usd |
| open / high / low / close | Positive USD prices; require low <= open/close <= high |
| volume | Nonnegative base-asset units for that daily candle |
| source / venue | Declared provenance; the API cannot authenticate uploaded data |
| coverage_end | Completed day bounding the upload; individual histories may end earlier |
| Limits | 20 markets, 730 bars per market, 15,000 bars total |
| Continuity | No duplicate or missing dates inside an individual market history |

```python
{
  "source": "Licensed exchange daily export",
  "venue": "my-source-venue", "quote_currency": "USD",
  "coverage_end": "2025-01-01",
  "candles": [{"date": "2025-01-01",
    "market_id": "bitcoin-usd", "open": "95000",
    "high": "97000", "low": "94000", "close": "96000",
    "volume": "1234.5678"}]
}
```

OHLC and volume are JSON decimal strings, with at most 12 decimal places and 28 total digits, bounded above by 10^15. Numerical analytical outputs use float64; this service is not a financial accounting ledger. Do not mix quote turnover with base volume or combine different venues under one series ID.

A date before today alone cannot prove a bar is genuine or correctly resampled. The uploader must establish UTC boundaries, venue, quote convention and instrument identity. Validation catches structural errors; it does not replace provider reconciliation.

# 06  Programming the import module

schemas.py validates individual candles before storage. imports.py then sorts by market/date, groups each market and checks continuity. No missing bar is forward-filled: invented flat prices would distort RSI, volatility and volume ratios.

```python
# Actual continuity check from imports.py
for market, bars in groups.items():
    if len(bars) > 730:
        raise ValueError("Use at most 730 daily candles per market.")
    days = [date.fromisoformat(x["date"]) for x in bars]
    for a, b in zip(days, days[1:]):
        if (b - a).days != 1:
            raise ValueError(
                f"{market}: duplicate or missing daily candle after {a}."
            )
```

## Preview before commit

POST /imports/preview accepts CSV text plus source, venue and coverage_end. It requires the exact seven-column header, parses rows into the same DatasetInput contract as JSON and returns canonical data plus a quality summary. It writes nothing to the database. The client can review the result, then submit the returned dataset to a workspace.

CSV rows are bounded; malformed columns and oversized row counts return validation errors. Error messages contain field locations and messages, not the complete original upload. Dataset deduplication hashes canonical rows and provenance within the workspace. A different source or venue intentionally produces a different fingerprint.

## Development plan for this module

First agree on units and market identifiers; then implement strict schemas and preview; finally verify duplicates, gaps, OHLC bounds, dates and round-trip imports. Later add provider adapters that explicitly normalize timestamps and volume units before calling this same boundary.

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

# 13  API contracts and integration

| Method / route | Purpose |
| --- | --- |
| POST /api/auth/register, /login | Create account or start server session |
| GET /api/auth/session; POST /logout | Retrieve session/CSRF information or revoke session |
| GET /api/v1/workspaces | List owned workspaces |
| POST /api/v1/workspaces | Create a named USD workspace |
| POST /api/v1/imports/preview | Validate CSV without storing it |
| GET /api/v1/workspaces/{id}/datasets | Retrieve owned dataset snapshots |
| POST /api/v1/workspaces/{id}/datasets | Commit validated JSON/preview result |
| POST /api/v1/workspaces/{id}/analyses | Save indicator, alert and model results |
| GET /api/v1/analyses; /analyses/{id} | List latest 100 reports or retrieve one |
| GET /api/v1/analyses/{id}/report | Export format=json, history or alerts |
| POST /api/v1/demo | Create synthetic workspace/dataset in empty account |

Create endpoints for workspaces, datasets, analyses and demo require Idempotency-Key. Protected POST requests require X-CSRF-Token and the session cookie. The preview requires CSRF but does not create a replay receipt because it does not persist business data.

Successful creates return 201; validation issues 422; unauthenticated access 401; CSRF/origin rejection 403; missing/foreign records 404; replay conflicts 409; authentication throttling 429. docs/openapi.json is generated from the working server, not handwritten separately.

# 14  Authentication and security coding

security.py hashes passwords with Argon2 and stores an opaque session-token digest rather than the raw browser token. A seven-day server session contains user ID, expiry and a separate CSRF token. The cookie is HttpOnly and SameSite=Lax; COOKIE_SECURE enables Secure when HTTPS is used.

```python
# Actual write protection from security.py
if request.method not in {"GET", "HEAD", "OPTIONS"}:
    require_trusted_origin(request)
    supplied = x_csrf_token or ""
    if not secrets.compare_digest(supplied, session.csrf_token):
        raise HTTPException(
            403, "The security token is missing or expired. "
            "Refresh and try again."
        )
```

Supplied browser Origin must match configured local origins. CLI clients may omit Origin but still need CSRF for authenticated writes. Registration/login use origin checks and throttling. Login verifies a dummy hash for unknown users to reduce trivial timing differences; the API returns a generic credential error.

## Owner isolation and error hygiene

Workspace and analysis reads use user-scoped SQL queries. A record belonging to another account returns 404. Validation responses contain field paths and messages without echoing submitted password values. API responses have no-store cache control; security headers include nosniff and frame denial.

The local login limiter allows 20 attempts per IP per five minutes and has bounded cleanup. It is in-process; multiple workers need a shared limiter and correct trusted-proxy configuration. Public production also needs HTTPS, credential/session lifecycle management, abuse controls and request-size limits. Those deployment tasks are not claimed as completed.

# 15  Atomic writes and replay behavior

services.mutation() computes a payload hash and looks up a replay receipt scoped to user and action. An identical retry returns the saved response. Reusing the key with a different payload returns 409. Database uniqueness also protects concurrent receipts for the same scope/key.

```python
# Actual receipt and commit from services.py
result = work()
db.add(RequestRecord(
    user_id=user.id, scope=scope, key=key,
    payload_hash=fingerprint, response=result
))
db.commit()
return result
```

work() flushes the business row but does not commit independently. The final commit saves the business record and replay receipt together. On an integrity conflict, the session rolls back and checks whether a matching committed receipt won the race; otherwise it returns a conflict. A validation failure does not create a partial analysis.

## Immutability and reproducibility

An analysis stores thresholds, selected IDs, source/venue, coverage, canonical candles, quality metadata, results, engine version and package versions. Export reads the saved report; it never recomputes it with today's prices. Deduplicated datasets remain scoped to a workspace.

Upgrade, downgrade and schema comparison were checked on an empty isolated SQLite database. That development check is not a production downgrade policy. Before upgrades in a real service, take backups and rehearse migration/restore against a representative database. PostgreSQL behavior and concurrent load require runtime verification in the target environment.

# 16  Using the API from an application

```python
# Analysis request after creating a dataset
payload = {
    "dataset_id": dataset_id, "as_of": "2025-06-29",
    "name": "Daily market review",
    "market_ids": ["bitcoin-usd"], "enable_ml": True,
    "rsi_low": 30, "rsi_high": 70,
    "volume_ratio_limit": 2,
    "daily_change_limit": 0.10, "volatility_limit": 0.80
}
client.headers["X-CSRF-Token"] = csrf_token
client.headers["Idempotency-Key"] = request_key
response = client.post(
    f"/api/v1/workspaces/{workspace_id}/analyses", json=payload
)
response.raise_for_status()
```

A cookie-aware HTTPX client stores the session after registration/login. Keep the CSRF token with the session. Generate one request key for each intended create and reuse that key/payload only on retries. A retry with changed thresholds is a new action and needs a new key.

## Complete supplied demonstration

scripts/demo_client.py registers a random account, generates two synthetic series, downloads their dataset, writes examples/candles.csv, previews/reimports it, saves a 360-row analysis, exports JSON/history/alerts, checks Swagger/OpenAPI and logs out. The script checks that clustering is available for both markets and writes examples/demo-report.json.

The demo client uses trust_env=False for predictable local HTTP access. It does not print the generated password. The files included in examples are synthetic snapshots created during verification. Existing accounts may create normal workspaces; demo specifically requires an empty workspace catalog.

# 17  Local run and Docker operation

```python
# From the extracted project root (Linux/macOS)
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8009

# Another terminal, project root, activated environment:
python scripts/demo_client.py --url http://127.0.0.1:8009
```

The default database is backend/trend.db when started from backend. Migrations create the schema explicitly; starting the API alone does not silently create tables. Use /docs for Swagger and /openapi.json for schema export. Windows activation instructions are included in README.md.

```python
# Docker/PostgreSQL alternative, project root:
cp .env.example .env
# Set POSTGRES_PASSWORD to a long random URL-safe value.
docker compose up --build
# Open http://localhost:8089/docs
```

Docker uses Python 3.12, complete pinned runtime dependencies and a nonroot process. The entrypoint applies Alembic then starts Uvicorn. Compose waits for PostgreSQL health, exposes only API localhost:8089 and keeps the database on its private network with a persistent named volume.

Docker is unavailable in the creation environment, so container execution and PostgreSQL migrations have not been tested here. SQLite migrations and the Python HTTP service were executed successfully. Public deployment needs HTTPS, Secure cookies, configured origins, backups, monitoring and shared throttling before launch.

# 18  Verification and observed results

| Check | Observed result |
| --- | --- |
| Automated suite | 43 tests passed; 2.66 seconds in the verification run |
| Reference calculations | SMA arithmetic, Wilder RSI example, MACD identity, Bollinger population std, ATR and volatility |
| Model chronology | 119-bar minimum; prefix predictions and centers unchanged when future bars are added |
| Import checks | Decimals, bounds, OHLC, UTC completion, missing/duplicate dates and coverage |
| Security / storage | CSRF, origins, ownership, idempotency conflicts, snapshots, login/logout and failed-write rollback |
| Real HTTP workflow | 360 synthetic candles; 2 markets; 64 explained historical alerts; ML available |
| API artifacts | CSV preview/import, 3 export formats, Swagger and generated OpenAPI passed |
| Migrations / quality | SQLite upgrade and schema comparison; Ruff formatting and lint passed |
| Not run | Docker/PostgreSQL runtime, public load tests and live provider ingestion |

One upstream Starlette warning recommends HTTPX2 for its TestClient adapter. Current TestClient tests and the separate real HTTPX client pass. The warning is documented rather than suppressed or confused with a failing request.

The synthetic price series includes a discontinuity and volume burst for alert coverage. It is deliberately artificial and is not evidence of real-world forecasting accuracy. The code tests rule calculations and historical model timing; future commercial model claims need separate evaluation on appropriately licensed real data.

# 19  Development plan by module

| Module / estimate | Programming tasks | Acceptance criterion |
| --- | --- | --- |
| 1. Contracts + ingest
2 days | Define dates, units and IDs; strict Pydantic schemas; CSV preview; canonical rows | Bad bars rejected; preview round-trips through save |
| 2. Auth + workspace
2 days | Argon2, sessions, CSRF, ownership and workspace endpoints | Foreign account cannot read or create against another workspace |
| 3. Indicator engine
2 days | TA-Lib arrays; explicit warm-up; volume and volatility conventions | Reference values and first-valid-bar tests pass |
| 4. Alert rules
1 day | Cross/entry events; daily threshold flags; evidence dictionaries | Each alert traceable to row and saved threshold |
| 5. Regime model
2 days | Features, earlier-only scaling/training, later labels and fallback statuses | No future leakage; deterministic prefix classifications |
| 6. Storage + exports
2 days | Dataset fingerprints, atomic replay, snapshots, JSON/CSV outputs | Same retry returns same record; failed write leaves no partial data |
| 7. Delivery + operation
2 days | Migrations, Docker, client, OpenAPI, documentation and review | Real HTTP flow passes; target Docker/PostgreSQL validated before release |

These are planning estimates for one experienced developer, not time already logged. The supplied baseline is implemented and tested as described. Allow 2-3 additional days for integration fixes and independent review: roughly 15-16 working days for a fresh build of comparable scope. Hosting/production work depends on the actual environment.

# 20  Roadmap, design and next stages

## Optional application screen design

A future dashboard can use the existing API without changing the analytics engine. Present a workspace selector, data source/coverage banner and as-of date first. Show latest close, trend, RSI and volatility per market; let the user open history, alert evidence and model baseline details. Unavailable metrics should visibly read "Insufficient history" rather than looking like a zero.

| Stage | Additions | Acceptance / estimate |
| --- | --- | --- |
| A. Dashboard | Charts for close/SMA/Bollinger, RSI and volume; import preview; reports | Render saved results exactly; honor null values and ownership / 4-6 days |
| B. Live ingestion | Allowlisted read-only provider adapters; UTC resampling; retries, rate limits and provenance | Discard incomplete bars; reconcile units; mocked and provider integration tests / 3-5 days |
| C. Scheduled monitoring | Job queue; daily analysis; deduplicated notifications and acknowledgements | Idempotent daily jobs and delivery retries / 3-4 days |
| D. Operational launch | PostgreSQL validation, HTTPS, shared limiter, backups, logging and retention | Restore rehearsal, load tests and monitored failures / 3-5 days |
| E. Predictive research | Define targets, walk-forward testing, baseline comparison and uncertainty | Independent out-of-sample evidence before forecasting claims / separately scoped |

The first version has Swagger and exports, not a custom chart dashboard. The proposed screens above are design guidance. Paid feeds or optional AI summaries can be integrated later with explicit terms, usage budgets and cached evidence; the current implementation requires neither.

# 21  Source map and technical references

| Location | Read it for |
| --- | --- |
| backend/app/schemas.py + imports.py | Input contracts, CSV preview and canonical history |
| backend/app/indicators.py + engine.py | Indicator calculations, as-of filtering and alerts |
| backend/app/regimes.py | Fixed historical baseline and clustering metadata |
| backend/app/routes.py + services.py | Owner-scoped API workflows, atomic create/replay and exports |
| backend/app/main.py + security.py | Login/session handling, CSRF, origin checks and error hygiene |
| backend/app/models.py + migrations/ | Persistent schema and versioned database setup |
| backend/tests/ + scripts/demo_client.py | Automated assertions and complete real HTTP example |
| docs/ + examples/ | OpenAPI, methodology, planning and synthetic demonstration |

## Primary references checked on 06 October 2026

TA-Lib Python project and installation: https://github.com/TA-Lib/ta-lib-python

TA-Lib indicator catalog: https://ta-lib.org/functions/

TA-Lib RSI and Wilder smoothing: https://ta-lib.org/functions/rsi.html

scikit-learn KMeans: https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html

scikit-learn StandardScaler: https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.StandardScaler.html

Versions in the guide match the tested pinned runtime. Source package licenses are separate from the project MIT license. Consult upstream installation and licensing instructions for your target platform. Future paid provider prices are intentionally not quoted because no provider is required or selected in this release.
