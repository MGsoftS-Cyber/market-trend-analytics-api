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
