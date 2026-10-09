"""Real HTTP smoke client. Run from project root after starting the API."""

import argparse
import csv
import json
import secrets
from pathlib import Path
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8009")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
with httpx.Client(base_url=args.url, trust_env=False, timeout=60) as client:
    assert client.get("/api/health").status_code == 200
    account = client.post(
        "/api/auth/register",
        json={
            "email": f"demo-{secrets.token_hex(6)}@example.test",
            "password": secrets.token_urlsafe(24),
        },
    )
    account.raise_for_status()
    client.headers["X-CSRF-Token"] = account.json()["csrf_token"]
    client.headers["Idempotency-Key"] = secrets.token_hex(12)
    d = client.post("/api/v1/demo")
    d.raise_for_status()
    demo = d.json()
    path = f"/api/v1/workspaces/{demo['workspace_id']}"
    dataset = client.get(path + "/datasets").json()[0]
    with (root / "examples/candles.csv").open("w", newline="") as f:
        keys = ["date", "market_id", "open", "high", "low", "close", "volume"]
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(dataset["candles"])
    preview = client.post(
        "/api/v1/imports/preview",
        json=dict(
            candles_csv=(root / "examples/candles.csv").read_text(),
            source=dataset["source"],
            venue=dataset["venue"],
            coverage_end=dataset["coverage_end"],
        ),
    )
    preview.raise_for_status()
    client.headers["Idempotency-Key"] = secrets.token_hex(12)
    imported = client.post(path + "/datasets", json=preview.json()["dataset"])
    imported.raise_for_status()
    client.headers["Idempotency-Key"] = secrets.token_hex(12)
    analysis = client.post(
        path + "/analyses",
        json={"dataset_id": imported.json()["id"], "as_of": demo["as_of"]},
    )
    analysis.raise_for_status()
    result = analysis.json()
    assert len(result["results"]["history"]) == 360
    assert all(
        x["model"]["status"] == "available" for x in result["results"]["markets"]
    )
    (root / "examples/demo-report.json").write_text(
        json.dumps(result, indent=2, allow_nan=False)
    )
    for fmt in ["json", "history", "alerts"]:
        r = client.get(
            f"/api/v1/analyses/{result['id']}/report", params={"format": fmt}
        )
        r.raise_for_status()
    schema = client.get("/openapi.json")
    schema.raise_for_status()
    (root / "docs/openapi.json").write_text(json.dumps(schema.json(), indent=2))
    assert client.get("/docs").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/session").status_code == 401
    print(
        "HTTP smoke passed: register, demo, CSV preview, import, analysis, three reports, Swagger, logout."
    )
    print(
        f"Synthetic candles: 360; markets: 2; alerts: {len(result['results']['alerts'])}; ML: available."
    )
