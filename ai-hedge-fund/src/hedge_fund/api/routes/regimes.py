"""Regime clustering over one company's price history.

Computed, not judged: no model is called on this route, so it needs no spend
guard and answers in about a second on ten years of daily bars — most of that
the Baum-Welch fit, which ``hmm=false`` skips.

The response carries the labelling *and* the score of the labelling, including
the score of the volatility-threshold rule this replaces, measured the same
way. A reader who wants to disbelieve the regimes has the number to do it
with, which is the point.

Alongside it sits a hidden Markov model of the same returns. Its labels are
scored on the same windows and usually come out worse; it is there for the
transition matrix — persistence, expected run length, and tomorrow's state —
which is the one question the clustering cannot be asked. See
:mod:`hedge_fund.regimes.hmm`.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from hedge_fund.agents.guardrails import GuardrailError, sanitize_ticker
from hedge_fund.data.service import get_data_service
from hedge_fund.regimes import DEFAULT_H1, DEFAULT_H2, analyse
from hedge_fund.regimes.wasserstein import RegimeError

logger = logging.getLogger(__name__)
router = APIRouter()
_ds = get_data_service()

_DATE_COLS = ("date", "index", "datetime", "timestamp")


def _series(df: pd.DataFrame) -> tuple[list[str], list[float]]:
    """Dates and closes out of whatever shape the provider handed back.

    Providers disagree on whether the date is the index or a column, and on
    its capitalisation. Guessing wrong here silently mislabels every episode
    by returning positional integers as dates, so it is explicit.
    """
    frame = df.reset_index()
    date_col = next(
        (c for c in frame.columns if str(c).strip().lower() in _DATE_COLS),
        None,
    )
    close_col = next(
        (c for c in frame.columns if str(c).strip().lower() == "close"),
        None,
    )
    if date_col is None or close_col is None:
        raise HTTPException(
            status_code=502,
            detail="price history arrived without a date or close column",
        )
    closes = pd.to_numeric(frame[close_col], errors="coerce")
    keep = closes.notna() & (closes > 0)
    return (
        [str(d)[:10] for d in frame.loc[keep, date_col]],
        [float(v) for v in closes[keep]],
    )


@router.get("/{ticker}")
def regimes(
    ticker: str,
    days: int = Query(default=2520, ge=400, le=7300),
    k: int = Query(default=2, ge=2, le=4),
    window_days: int = Query(default=DEFAULT_H1, ge=21, le=252),
    overlap_days: int = Query(default=DEFAULT_H2, ge=0, le=240),
    seed: int = Query(default=0, ge=0, le=10_000),
    hmm: bool = Query(default=True, description="Fit the hidden Markov model too."),
) -> dict[str, Any]:
    """Cluster a company's return distributions into regimes, and score the fit."""
    try:
        symbol = sanitize_ticker(ticker)
    except GuardrailError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if overlap_days >= window_days:
        raise HTTPException(
            status_code=400,
            detail=f"overlap_days must be below window_days ({window_days})",
        )

    try:
        df = _ds.get_price_history(symbol, days=days)
    except Exception as exc:
        logger.exception("%s: price fetch failed", symbol)
        raise HTTPException(status_code=502, detail=f"price fetch failed: {exc}") from exc
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"no price history for {symbol}")

    dates, closes = _series(df)
    try:
        result = analyse(
            np.asarray(closes, dtype=float),
            dates,
            ticker=symbol,
            k=k,
            h1=window_days,
            h2=overlap_days,
            seed=seed,
            with_hmm=hmm,
        )
    except RegimeError as exc:
        # A short listing is the ordinary case, not a server fault: say what
        # is missing rather than returning an empty chart.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return result.as_dict()
