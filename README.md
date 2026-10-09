# Market Trend Analytics API - v1.0.0

Daily crypto spot market analysis: SMA20/50, Wilder RSI14, MACD12/26/9, Bollinger20, ATR14, volume ratios, 20-day annualized historical volatility, explained alerts, and optional KMeans market-regime clustering. Includes account authentication, owner-scoped workspaces, CSV previews, immutable datasets/reports, JSON/CSV exports, OpenAPI and an offline demo.

**Free local operation.** No paid AI service, wallet, exchange credential or cloud server is required. This release imports CSV/JSON; live exchange ingestion and automated notifications are future work. Swagger is the supplied API interface; no separate dashboard is included.

## Start locally with Python 3.12

From the extracted project root (Linux/macOS):

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8009
```

On Windows, create the environment with `py -3.12 -m venv .venv`, activate `.venv\Scripts\Activate.ps1`, then use the same pip/Alembic/Uvicorn commands. TA-Lib uses binary wheels when available; unsupported platforms may require the upstream C library.

Open http://localhost:8009/docs. Register using a valid email and a password of 12-128 characters. Cookie authentication happens automatically in a same-origin browser. Copy the returned `csrf_token` into `X-CSRF-Token` for protected POST requests. Supply a fresh `Idempotency-Key` for each create; reuse it only when retrying the same payload.

In another terminal, from the project root with the environment activated:

```sh
python scripts/demo_client.py --url http://127.0.0.1:8009
```

This real HTTP client creates a random local demo account, generates synthetic candles, previews/imports CSV, saves an analysis, downloads three report formats and logs out. It writes reusable candles and a report to `examples/`. It does not print its password.

## Start with Docker and PostgreSQL

```sh
cp .env.example .env
# Edit POSTGRES_PASSWORD to a long random URL-safe password.
docker compose up --build
```

Open http://localhost:8089/docs. API exposure is limited to localhost; PostgreSQL uses a private container network and persistent named volume. Run the client with `--url http://127.0.0.1:8089`. Docker/PostgreSQL configuration is supplied but could not be executed in the creation environment (Docker is unavailable). Do not use `docker compose down -v` unless intentionally deleting database data.

## Import real candles

Use `POST /api/v1/imports/preview` with `candles_csv`, `source`, `venue` and `coverage_end`. The exact CSV header is:

```csv
date,market_id,open,high,low,close,volume
2025-01-01,bitcoin-usd,95000,97000,94000,96000,1234.5678
```

Volume means base-asset units, not quote turnover or number of trades. Use one venue, USD spot quote and UTC completed daily candles. Send decimal strings in JSON. Keep consistent market IDs such as `bitcoin-usd`. Maximum: 20 markets, 730 candles per market, 15,000 rows overall. Missing/duplicate days and incomplete current-day bars are rejected. The API cannot prove that uploaded source labels or numbers are accurate.

Create a workspace, POST the preview's `dataset` to its `/datasets`, then POST `/analyses` with the returned `dataset_id` and `as_of`. Every selected market must have an exact bar on `as_of`; later bars are excluded from calculations. Full earlier history remains available for indicator warm-up. See `docs/API.md` and `docs/openapi.json`.

## Methodology and boundaries

Ratios are fractions: daily_return 0.02 means 2%; volatility20 0.8 means 80% annualized historical volatility using 365 days and sample standard deviation. Indicators unavailable during warm-up are JSON null. Trend compares SMA20 to SMA50. KMeans needs at least 119 contiguous bars: 49 warm-up + 60 training + at least 10 later classifications. Scaling and fitting use only the first 60 complete feature rows. Relative regime labels describe that market's baseline; they do not predict returns or provide confidence probabilities. RSI, MACD and ATR follow the pinned TA-Lib conventions.

This release provides historical analytics, not backtested trading profitability, investment advice, tax accounting, order execution, derivatives risk or intraday signals. Authentication uses Argon2 and server-side sessions. Local rate limiting is in process; public multi-worker deployment needs shared throttling, HTTPS, secure cookies, request-size limits, retention policy and operational review.

## Verification

From `backend`:

```sh
ruff format --check app tests migrations
ruff check app tests migrations
pytest -q
alembic upgrade head
alembic check
```

43 tests pass. Real HTTP demo, imports, exports, OpenAPI and logout pass. Migration upgrade/schema comparison pass with SQLite. Docker/PostgreSQL runtime was not tested. One upstream Starlette deprecation warning concerns HTTPX used by TestClient; current tests and real HTTP client pass.

## Files

- `backend/app/`: API, security, contracts, imports, indicators, regime model and storage workflows.
- `backend/tests/`: calculation and API/security tests.
- `backend/migrations/`: versioned Alembic schema.
- `backend/requirements.lock.txt`: complete pinned runtime dependencies.
- `scripts/demo_client.py`: complete real HTTP example.
- `examples/`: synthetic candles and saved report.
- `docs/`: conception, methodology, API, module plan, verification and OpenAPI.

MIT project license. Dependencies retain their own licenses; review them before commercial redistribution.
