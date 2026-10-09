"""Owner-scoped workspace workflows and immutable analysis evidence."""

import csv
import io
import json
import hashlib
import math
from datetime import timedelta
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select
from .database import get_db
from .security import current_user
from .models import Workspace, Dataset, Analysis
from .schemas import WorkspaceInput, DatasetInput, CsvInput, AnalysisInput, utc_today
from .services import mutation
from .imports import preview, normalize
from .engine import evaluate, ENGINE_VERSION

router = APIRouter(prefix="/api/v1")
Key = Header(min_length=1, max_length=100)


def owned_workspace(db, identifier, user):
    obj = db.scalar(select(Workspace).where(Workspace.id == identifier, Workspace.user_id == user.id))
    if not obj:
        raise HTTPException(404, "Workspace not found in your account.")
    return obj


def owned_analysis(db, identifier, user):
    obj = db.scalar(select(Analysis).join(Workspace).where(Analysis.id == identifier, Workspace.user_id == user.id))
    if not obj:
        raise HTTPException(404, "Analysis not found in your account.")
    return obj


def workspace_view(x):
    return dict(id=x.id, name=x.name, quote_currency=x.quote_currency)


def dataset_view(x):
    return dict(
        id=x.id,
        workspace_id=x.workspace_id,
        source=x.source,
        coverage_end=x.coverage_end,
        candles=x.candles,
        venue=x.venue,
        quote_currency="USD",
        quality=x.quality,
        created_at=x.created_at,
    )


def analysis_view(x):
    return dict(
        id=x.id,
        workspace_id=x.workspace_id,
        dataset_id=x.dataset_id,
        inputs=x.inputs,
        results=x.results,
        engine_version=x.engine_version,
        created_at=x.created_at,
    )


@router.get("/workspaces")
def workspaces(user=Depends(current_user), db=Depends(get_db)):
    return [workspace_view(x) for x in db.scalars(select(Workspace).where(Workspace.user_id == user.id))]


@router.post("/workspaces", status_code=201)
def create_workspace(data: WorkspaceInput, idempotency_key: str = Key, user=Depends(current_user), db=Depends(get_db)):
    def work():
        x = Workspace(user_id=user.id, **data.model_dump())
        db.add(x)
        db.flush()
        return workspace_view(x)

    return mutation(db, user, "workspace", idempotency_key, data.model_dump(mode="json"), work)


@router.post("/imports/preview")
def preview_import(data: CsvInput, user=Depends(current_user)):
    try:
        return preview(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/workspaces/{identifier}/datasets")
def datasets(identifier: str, user=Depends(current_user), db=Depends(get_db)):
    owned_workspace(db, identifier, user)
    return [
        dataset_view(x)
        for x in db.scalars(
            select(Dataset).where(Dataset.workspace_id == identifier).order_by(Dataset.created_at.desc())
        )
    ]


@router.post("/workspaces/{identifier}/datasets", status_code=201)
def create_dataset(
    identifier: str, data: DatasetInput, idempotency_key: str = Key, user=Depends(current_user), db=Depends(get_db)
):
    owned_workspace(db, identifier, user)
    try:
        candles, quality = normalize(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    fingerprint = hashlib.sha256(
        json.dumps(
            dict(candles=candles, venue=data.venue, source=data.source, coverage_end=str(data.coverage_end)),
            sort_keys=True,
        ).encode()
    ).hexdigest()

    def work():
        prior = db.scalar(select(Dataset).where(Dataset.workspace_id == identifier, Dataset.fingerprint == fingerprint))
        if prior:
            return dataset_view(prior)
        x = Dataset(
            workspace_id=identifier,
            source=data.source,
            coverage_end=str(data.coverage_end),
            candles=candles,
            venue=data.venue,
            quality=quality,
            fingerprint=fingerprint,
        )
        db.add(x)
        db.flush()
        return dataset_view(x)

    return mutation(db, user, "dataset:" + identifier, idempotency_key, data.model_dump(mode="json"), work)


@router.post("/workspaces/{identifier}/analyses", status_code=201)
def analyze(
    identifier: str, data: AnalysisInput, idempotency_key: str = Key, user=Depends(current_user), db=Depends(get_db)
):
    p = owned_workspace(db, identifier, user)
    d = db.scalar(select(Dataset).where(Dataset.id == data.dataset_id, Dataset.workspace_id == identifier))
    if not d:
        raise HTTPException(404, "Dataset not found in this workspace.")
    inputs = dict(
        **data.model_dump(mode="json"),
        workspace=workspace_view(p),
        source=d.source,
        coverage_end=d.coverage_end,
        candles=d.candles,
        venue=d.venue,
        quality=d.quality,
    )

    def work():
        try:
            results = evaluate(inputs)
            json.dumps(results, allow_nan=False)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        x = Analysis(
            workspace_id=identifier, dataset_id=d.id, inputs=inputs, results=results, engine_version=ENGINE_VERSION
        )
        db.add(x)
        db.flush()
        return analysis_view(x)

    return mutation(db, user, "analysis:" + identifier, idempotency_key, data.model_dump(mode="json"), work)


@router.get("/analyses")
def analyses(user=Depends(current_user), db=Depends(get_db)):
    return [
        analysis_view(x)
        for x in db.scalars(
            select(Analysis)
            .join(Workspace)
            .where(Workspace.user_id == user.id)
            .order_by(Analysis.created_at.desc())
            .limit(100)
        )
    ]


@router.get("/analyses/{identifier}")
def get_analysis(identifier: str, user=Depends(current_user), db=Depends(get_db)):
    return analysis_view(owned_analysis(db, identifier, user))


@router.get("/analyses/{identifier}/report")
def report(identifier: str, format: str = "json", user=Depends(current_user), db=Depends(get_db)):
    x = owned_analysis(db, identifier, user)
    if format == "json":
        text, media = json.dumps(analysis_view(x), indent=2), "application/json"
    elif format in {"history", "alerts"}:
        keys = (
            [
                "date",
                "market_id",
                "close",
                "volume",
                "sma20",
                "sma50",
                "rsi14",
                "atr14",
                "macd",
                "macd_signal",
                "macd_histogram",
                "bb_upper",
                "bb_middle",
                "bb_lower",
                "daily_return",
                "return20",
                "volatility20",
                "volume_baseline20",
                "volume_ratio",
                "trend",
                "regime",
            ]
            if format == "history"
            else ["date", "market_id", "code", "message", "evidence"]
        )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(keys)
        for row in x.results[format]:
            values = []
            for k in keys:
                v = row.get(k)
                if isinstance(v, dict):
                    v = json.dumps(v, sort_keys=True)
                if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")):
                    v = "'" + v
                values.append(v)
            writer.writerow(values)
        text, media = output.getvalue(), "text/csv"
    else:
        raise HTTPException(422, "Use json, history or alerts format.")
    ext = "json" if format == "json" else "csv"
    return Response(
        text, media_type=media, headers={"Content-Disposition": f'attachment; filename="trend-{format}-{x.id}.{ext}"'}
    )


@router.post("/demo", status_code=201)
def demo(idempotency_key: str = Key, user=Depends(current_user), db=Depends(get_db)):
    def work():
        if db.scalar(select(Workspace).where(Workspace.user_id == user.id)):
            raise HTTPException(409, "Demo requires an empty workspace catalog.")
        p = Workspace(user_id=user.id, name="Synthetic Market Watch", quote_currency="USD")
        db.add(p)
        db.flush()
        end = utc_today() - timedelta(days=1)
        start = end - timedelta(days=179)
        candles = []
        for market, base in [("bitcoin-usd", 50000), ("ethereum-usd", 2500)]:
            previous = base
            for i in range(180):
                close = base * (1 + 0.001 * i + 0.055 * math.sin(i * 0.22)) * (0.82 if i >= 155 else 1)
                opening = previous
                candles.append(
                    dict(
                        date=str(start + timedelta(days=i)),
                        market_id=market,
                        open=f"{opening:.8f}",
                        high=f"{max(opening, close) * 1.02:.8f}",
                        low=f"{min(opening, close) * 0.98:.8f}",
                        close=f"{close:.8f}",
                        volume=f"{(1200 + 200 * math.sin(i * 0.4)) * (4 if i == 155 else 1):.8f}",
                    )
                )
                previous = close
        data = DatasetInput(source="Synthetic offline demonstration", venue="demo", coverage_end=end, candles=candles)
        rows, quality = normalize(data)
        d = Dataset(
            workspace_id=p.id,
            source=data.source,
            venue=data.venue,
            coverage_end=str(end),
            candles=rows,
            quality=quality,
            fingerprint=hashlib.sha256(
                json.dumps(
                    dict(candles=rows, venue=data.venue, source=data.source, coverage_end=str(end)), sort_keys=True
                ).encode()
            ).hexdigest(),
        )
        db.add(d)
        db.flush()
        return dict(
            workspace_id=p.id, dataset_id=d.id, as_of=str(end), message="Synthetic candles; no live feed connected."
        )

    return mutation(db, user, "demo", idempotency_key, {}, work)
