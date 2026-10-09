"""Daily USD spot candle contracts. Prices and volumes arrive as decimal strings."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import Field, field_validator, model_validator
from .auth_schemas import Credentials, StrictModel  # noqa: F401

Number = Annotated[Decimal, Field(ge=0, le=Decimal("1e15"), max_digits=28, decimal_places=12, allow_inf_nan=False)]
Market = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]


def utc_today():
    return datetime.now(timezone.utc).date()


class WorkspaceInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    quote_currency: Literal["USD"] = "USD"


class CandleInput(StrictModel):
    date: date
    market_id: Market
    open: Number
    high: Number
    low: Number
    close: Number
    volume: Number

    @field_validator("open", "high", "low", "close", "volume", mode="before")
    @classmethod
    def strings(cls, v):
        if not isinstance(v, str):
            raise ValueError("Send OHLC prices and base-asset volume as decimal strings.")
        return v

    @model_validator(mode="after")
    def valid(self):
        if self.date >= utc_today():
            raise ValueError("Only completed UTC daily candles are accepted.")
        if self.low <= 0 or not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("Require 0 < low <= open/close <= high.")
        return self


class DatasetInput(StrictModel):
    source: str = Field(min_length=1, max_length=200)
    venue: str = Field(min_length=1, max_length=80)
    quote_currency: Literal["USD"] = "USD"
    coverage_end: date
    candles: list[CandleInput] = Field(min_length=1, max_length=15000)

    @field_validator("coverage_end")
    @classmethod
    def completed(cls, v):
        if v >= utc_today():
            raise ValueError("Coverage end must be a completed UTC day.")
        return v


class CsvInput(StrictModel):
    candles_csv: str = Field(min_length=1, max_length=4000000)
    source: str = Field(min_length=1, max_length=200)
    venue: str = Field(min_length=1, max_length=80)
    coverage_end: date
    quote_currency: Literal["USD"] = "USD"


class AnalysisInput(StrictModel):
    dataset_id: str = Field(min_length=1, max_length=36)
    as_of: date
    name: str = Field(default="Market trend review", min_length=1, max_length=120)
    market_ids: list[Market] | None = Field(default=None, min_length=1, max_length=20)
    enable_ml: bool = True
    rsi_low: float = Field(default=30, gt=0, lt=100, allow_inf_nan=False)
    rsi_high: float = Field(default=70, gt=0, lt=100, allow_inf_nan=False)
    volume_ratio_limit: float = Field(default=2, ge=1, le=100, allow_inf_nan=False)
    daily_change_limit: float = Field(default=0.1, gt=0, le=10, allow_inf_nan=False)
    volatility_limit: float = Field(default=0.8, gt=0, le=10, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid(self):
        if self.rsi_low >= self.rsi_high:
            raise ValueError("RSI low must be below RSI high.")
        if self.market_ids is not None and len(set(self.market_ids)) != len(self.market_ids):
            raise ValueError("Use distinct market IDs.")
        return self
