# Verification - 06 October 2026

## Executed

- Python 3.12.14; direct versions and complete runtime lock installed.
- 43 pytest cases passed: reference indicator calculations, null warm-up, prior-only volume baseline, sample volatility, CSV constraints, model chronology, ownership, replay, login/logout, CSRF, origin rejection, validation error hygiene and failed writes.
- Ruff formatting and lint checks passed for app/tests/migrations; example client uses the same project Ruff configuration.
- SQLite Alembic upgrade, downgrade on an isolated empty database, re-upgrade and schema comparison passed.
- Uvicorn + real HTTPX client: health, account registration, synthetic demo, CSV export/preview/import, analysis, JSON/history/alerts exports, Swagger/OpenAPI and logout passed.
- Demo: 360 daily candles across two markets, 64 explained historical alerts, optional model available for both markets.
- PDF: 22 pages, rendered for visual review; diagrams, code and tables checked. No blank pages or overflow.
- ZIP: files and byte contents checked against source, excluding environments, databases, caches and secrets.

## Limits

Docker is unavailable here. Docker/PostgreSQL runtime, public load tests, HTTPS deployment and actual provider feeds were not executed. This version imports CSV/JSON and does not include a live provider adapter, scheduler, order execution or custom dashboard. Synthetic data does not demonstrate financial forecasting performance.

Starlette emits a TestClient deprecation warning recommending HTTPX2. Current tests and the independent real HTTPX client pass; the warning was not suppressed.
