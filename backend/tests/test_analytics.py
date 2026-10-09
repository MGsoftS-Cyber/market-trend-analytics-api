import copy
import math
from datetime import date, timedelta
import numpy as np
import pytest
from pydantic import ValidationError
from app.schemas import CandleInput, DatasetInput, AnalysisInput, CsvInput, utc_today
from app.imports import normalize, preview
from app.indicators import calculate
from app.regimes import classify
from app.engine import evaluate


def bars(n=180, kind="wave"):
    start = date(2025, 1, 1)
    result = []
    for i in range(n):
        price = (
            100 + i
            if kind == "up"
            else 100 - i * 0.2
            if kind == "down"
            else 100
            if kind == "flat"
            else 100 + 0.1 * i + 8 * math.sin(i * 0.2)
        )
        result.append(
            dict(
                date=str(start + timedelta(days=i)),
                market_id="bitcoin-usd",
                open=f"{price:.8f}",
                high=f"{price + 2:.8f}",
                low=f"{price - 2:.8f}",
                close=f"{price:.8f}",
                volume="100",
            )
        )
    return result


def inputs(rows=None, **kwargs):
    rows = rows or bars()
    return dict(
        candles=rows,
        as_of=rows[-1]["date"],
        coverage_end=rows[-1]["date"],
        market_ids=None,
        enable_ml=True,
        rsi_low=30,
        rsi_high=70,
        volume_ratio_limit=2,
        daily_change_limit=0.1,
        volatility_limit=0.8,
        **kwargs,
    )


def test_sma_arithmetic():
    h = calculate(bars(kind="up"))
    assert h[18]["sma20"] is None
    assert h[19]["sma20"] == pytest.approx(109.5)
    assert h[48]["sma50"] is None
    assert h[49]["sma50"] == pytest.approx(124.5)
    assert h[-1]["trend"] == "up"


@pytest.mark.parametrize("kind,expected", [("up", 100), ("down", 0), ("flat", 0)])
def test_rsi_native_conventions(kind, expected):
    h = calculate(bars(kind=kind))
    assert h[13]["rsi14"] is None
    assert h[14]["rsi14"] == pytest.approx(expected)


def test_macd_warmup_and_identity():
    h = calculate(bars())
    assert h[32]["macd"] is None
    assert h[33]["macd"] is not None
    assert h[-1]["macd_histogram"] == pytest.approx(h[-1]["macd"] - h[-1]["macd_signal"])


def test_bollinger_population_std():
    h = calculate(bars(kind="up"))
    assert h[19]["bb_upper"] == pytest.approx(109.5 + 2 * np.std(np.arange(100, 120), ddof=0))
    assert h[19]["bb_lower"] == pytest.approx(109.5 - 2 * np.std(np.arange(100, 120), ddof=0))


def test_atr_flat_range():
    h = calculate(bars(kind="flat"))
    assert h[13]["atr14"] is None
    assert h[14]["atr14"] == pytest.approx(4)


def test_volume_baseline_excludes_current():
    b = bars(25)
    b[-1]["volume"] = "1000"
    h = calculate(b)
    assert h[19]["volume_ratio"] is None
    assert h[-1]["volume_baseline20"] == 100
    assert h[-1]["volume_ratio"] == 10
    alert = [x for x in evaluate(inputs(b))["alerts"] if x["code"] == "VOLUME_SPIKE"]
    assert len(alert) == 1
    assert alert[0]["evidence"]["value"] == 10


def test_volatility_sample_std_and_365_days():
    b = bars(25)
    h = calculate(b)
    cl = np.array([float(x["close"]) for x in b])
    r = cl[1:] / cl[:-1] - 1
    assert h[19]["volatility20"] is None
    assert h[20]["volatility20"] == pytest.approx(np.std(r[:20], ddof=1) * math.sqrt(365))


def test_short_history_does_not_invent_alerts():
    result = evaluate(inputs(bars(1)))
    assert result["history"][0]["daily_return"] is None
    assert result["alerts"] == []
    assert result["markets"][0]["model"]["status"] == "insufficient_history"


def test_model_training_never_uses_future():
    first = classify(calculate(bars(140)), True)
    longer = classify(calculate(bars(180)), True)
    assert first["status"] == "available"
    assert first["centers"] == longer["centers"]
    assert first["predictions"] == longer["predictions"][: len(first["predictions"])]
    assert first["training_end"] < first["scoring_start"]


@pytest.mark.parametrize("n,status", [(118, "insufficient_history"), (119, "available")])
def test_model_minimum(n, status):
    assert classify(calculate(bars(n)), True)["status"] == status


def test_model_degenerate_and_disabled():
    h = calculate(bars(kind="flat"))
    assert classify(h, True)["status"] == "degenerate_training_data"
    assert classify(h, False)["status"] == "disabled"


def test_asof_hides_future_candles():
    b = bars()
    a = inputs(b)
    a["as_of"] = b[139]["date"]
    result = evaluate(a)
    assert result["markets"][0]["bars_used"] == 140
    assert result["history"][-1]["date"] == a["as_of"]
    assert result["markets"][0]["model"] == evaluate(inputs(b[:140]))["markets"][0]["model"]


@pytest.mark.parametrize("field,value", [("as_of", "2025-12-31"), ("market_ids", ["absent-usd"])])
def test_invalid_analysis_selection(field, value):
    data = inputs()
    data[field] = value
    with pytest.raises(ValueError):
        evaluate(data)


def test_exact_asof_bar_required():
    data = inputs()
    data["coverage_end"] = "2025-12-31"
    data["as_of"] = "2025-10-01"
    with pytest.raises(ValueError, match="exact completed"):
        evaluate(data)


@pytest.mark.parametrize(
    "change",
    [{"close": 100}, {"low": "0"}, {"high": "50"}, {"volume": "-1"}, {"close": "NaN"}, {"date": str(utc_today())}],
)
def test_candle_contract(change):
    row = bars(1)[0]
    row.update(change)
    with pytest.raises(ValidationError):
        CandleInput(**row)


@pytest.mark.parametrize("kind", ["duplicate", "gap", "after_coverage"])
def test_normalize_rejects_bad_history(kind):
    b = bars(5)
    if kind == "duplicate":
        b.append(copy.deepcopy(b[-1]))
    if kind == "gap":
        b.pop(2)
    end = b[-1]["date"] if kind != "after_coverage" else b[-2]["date"]
    data = DatasetInput(source="test", venue="test", coverage_end=end, candles=b)
    with pytest.raises(ValueError):
        normalize(data)


def test_preview_exact_header_and_valid_data():
    header = "date,market_id,open,high,low,close,volume\n"
    row = bars(1)[0]
    text = header + ",".join(row[k] for k in header.strip().split(","))
    data = CsvInput(candles_csv=text, source="test", venue="test", coverage_end=row["date"])
    assert preview(data)["quality"]["row_count"] == 1
    with pytest.raises(ValueError):
        preview(data.model_copy(update={"candles_csv": "date,close\n2025-01-01,100"}))


def test_threshold_order_validation():
    with pytest.raises(ValidationError):
        AnalysisInput(dataset_id="id", as_of="2025-01-01", rsi_low=80, rsi_high=70)


def test_rsi_wilder_reference():
    prices = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
    b = bars(15)
    for row, p in zip(b, prices):
        row.update(open=str(p), high=str(p + 1), low=str(p - 1), close=str(p))
    assert calculate(b)[14]["rsi14"] == pytest.approx(70.464135, abs=1e-6)


def test_cross_alerts_require_previous_ready_values():
    result = evaluate(inputs(bars()))
    sma = [x for x in result["alerts"] if x["code"].startswith("SMA_CROSS")]
    assert sma
    assert all(x["date"] > bars()[49]["date"] for x in sma)
    assert all(x["evidence"]["before"] * x["evidence"]["after"] <= 0 for x in sma)


def test_zero_volume_baseline_is_null():
    b = bars(25)
    for row in b:
        row["volume"] = "0"
    b[-1]["volume"] = "100"
    assert calculate(b)[-1]["volume_ratio"] is None


def test_json_outputs_have_no_nan():
    import json

    json.dumps(evaluate(inputs(bars(3))), allow_nan=False)
