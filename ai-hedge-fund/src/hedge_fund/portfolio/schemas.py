"""Pydantic models for portfolio API."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class BuyRequest(BaseModel):
    ticker: str
    shares: Decimal = Field(gt=0)
    price_per_share: Decimal = Field(gt=0)
    fee: Decimal = Field(default=Decimal("0"), ge=0)
    note: str | None = None


class SellRequest(BaseModel):
    ticker: str
    shares: Decimal = Field(gt=0)
    price_per_share: Decimal = Field(gt=0)
    fee: Decimal = Field(default=Decimal("0"), ge=0)
    note: str | None = None


class CashRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    note: str | None = None


class SplitRequest(BaseModel):
    ticker: str
    ratio: Decimal = Field(gt=0, description="Forward split ratio, e.g. 4 for 4:1")
    ex_date: date | None = None
    note: str | None = None


class DividendRequest(BaseModel):
    ticker: str
    dividend_per_share: Decimal = Field(gt=0)
    note: str | None = None


class HoldingPatch(BaseModel):
    shares: Decimal | None = Field(default=None, gt=0)
    avg_cost: Decimal | None = Field(default=None, gt=0)


class TransactionOut(BaseModel):
    id: int
    txn_type: str
    ticker: str | None
    shares: float | None
    price_per_share: float | None
    fee: float
    cash_delta: float
    note: str | None
    executed_at: datetime
    meta: dict[str, Any] | None

    model_config = {"from_attributes": True}
