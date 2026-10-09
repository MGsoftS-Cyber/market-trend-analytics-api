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
