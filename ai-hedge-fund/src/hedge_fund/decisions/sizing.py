"""Size a candidate against the book you already own.

Most research tooling evaluates a name in isolation and stops at "is this
good?". The question that actually decides a trade is different: *given what I
already hold*, what does adding this do? A high-conviction name that moves with
everything you own adds risk without adding much diversification, and a
mediocre one that moves differently can still earn its place.

Everything here is computed from prices and the current book — no model is
involved, so the numbers are reproducible and the reasoning is inspectable.
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TRADING_DAYS = 252
# Below this many overlapping observations a correlation is not worth quoting.
MIN_OVERLAP = 60
# Weight above which a single position starts to dominate outcomes.
CONCENTRATION_WARN_PCT = 25.0
# Correlation above which an addition is mostly more of what you already own.
HIGH_CORRELATION = 0.75


@dataclass
class SizingAssessment:
    ticker: str
    proposed_value: float
    currency: str

    portfolio_value_before: float = 0.0
    portfolio_value_after: float = 0.0
    cash_before: float = 0.0
    cash_after: float = 0.0
    funded_by_cash: bool = True

    existing_weight_pct: float | None = None
    proposed_weight_pct: float | None = None
    rank_after: int | None = None
    holdings_after: int | None = None

    concentration_top3_before_pct: float | None = None
    concentration_top3_after_pct: float | None = None
    herfindahl_before: float | None = None
    herfindahl_after: float | None = None

    correlation_to_book: float | None = None
    overlap_observations: int | None = None
    candidate_volatility_pct: float | None = None
    portfolio_volatility_before_pct: float | None = None
    portfolio_volatility_after_pct: float | None = None
    volatility_change_pct: float | None = None
    diversifying: bool | None = None

    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _finite(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _returns(df: pd.DataFrame) -> pd.Series | None:
    if df is None or df.empty or "close" not in df:
        return None
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(close) < 3:
        return None
    rets = close.pct_change().dropna()
    rets.index = pd.to_datetime(rets.index)
    return rets[np.isfinite(rets.to_numpy())]


def _book_returns(
    holdings: list[dict[str, Any]], data_service: Any, days: int
) -> tuple[pd.Series | None, list[str]]:
    """Value-weighted daily returns for the existing book.

    Weighted by current market value, which is the honest approximation: it
    assumes today's weights held over the window rather than reconstructing the
    actual historical path, and that assumption is stated rather than hidden.
    """
    notes: list[str] = []
    series: dict[str, pd.Series] = {}
    weights: dict[str, float] = {}

    for h in holdings:
        ticker = h.get("ticker")
        mv = _finite(h.get("market_value")) or 0.0
        if not ticker or mv <= 0:
            continue
        try:
            rets = _returns(data_service.get_price_history(ticker, days=days))
        except Exception as e:
            logger.debug("No history for %s: %s", ticker, e)
            rets = None
        if rets is None or rets.empty:
            notes.append(f"{ticker}: no usable price history, excluded from the risk figures")
            continue
        series[ticker] = rets
        weights[ticker] = mv

    if not series:
        return None, notes

    frame = pd.DataFrame(series).dropna(how="all")
    if frame.empty:
        return None, notes

    total = sum(weights.values())
    w = pd.Series({t: weights[t] / total for t in frame.columns})
    # Missing days are treated as flat for that name rather than dropping the
    # whole row, which would otherwise discard a day because one holding is new.
    book = (frame.fillna(0.0) * w).sum(axis=1)
    return book, notes


def assess_addition(
    *,
    ticker: str,
    proposed_value: float,
    portfolio: dict[str, Any],
    data_service: Any,
    days: int = 365,
) -> SizingAssessment:
    """What adding `proposed_value` of `ticker` does to this portfolio."""
    ticker = ticker.strip().upper()
    holdings = [h for h in (portfolio.get("holdings") or []) if h.get("ticker")]
    total_before = _finite(portfolio.get("total_value")) or 0.0
    cash_before = _finite(portfolio.get("cash")) or 0.0

    a = SizingAssessment(
        ticker=ticker,
        proposed_value=round(proposed_value, 2),
        currency=str(portfolio.get("currency") or "USD"),
        portfolio_value_before=round(total_before, 2),
        cash_before=round(cash_before, 2),
    )

    existing = next((h for h in holdings if h["ticker"].upper() == ticker), None)
    existing_value = _finite(existing.get("market_value")) if existing else 0.0
    a.existing_weight_pct = _finite(existing.get("weight_pct")) if existing else 0.0

    # Buying with cash moves money between buckets; total value is unchanged.
    a.portfolio_value_after = round(total_before, 2)
    a.cash_after = round(cash_before - proposed_value, 2)
    a.funded_by_cash = a.cash_after >= 0
    if not a.funded_by_cash:
        a.flags.append(
            f"exceeds available cash by {abs(a.cash_after):,.0f} {a.currency} — "
            "this needs funding from a sale or a deposit"
        )
        # Value the enlarged book as if funded externally so the weights still
        # mean something rather than silently going negative.
        a.portfolio_value_after = round(total_before + (proposed_value - cash_before), 2)

    new_value = (existing_value or 0.0) + proposed_value
    # `total_value` includes cash, so a cash-funded buy leaves it unchanged. The
    # floor guards a degenerate book (a reported total smaller than the position
    # itself), which would otherwise yield a weight in the thousands of percent.
    denom = max(a.portfolio_value_after, new_value, 1.0)
    a.proposed_weight_pct = round(new_value / denom * 100, 2)

    # --- concentration ---------------------------------------------------
    weights_before = sorted(((_finite(h.get("weight_pct")) or 0.0) for h in holdings), reverse=True)
    after_map = {h["ticker"].upper(): (_finite(h.get("market_value")) or 0.0) for h in holdings}
    after_map[ticker] = new_value
    weights_after = sorted((v / denom * 100 for v in after_map.values()), reverse=True)

    a.holdings_after = len(after_map)
    a.rank_after = sorted(after_map, key=lambda k: after_map[k], reverse=True).index(ticker) + 1
    a.concentration_top3_before_pct = round(sum(weights_before[:3]), 2) if weights_before else 0.0
    a.concentration_top3_after_pct = round(sum(weights_after[:3]), 2)
    a.herfindahl_before = round(sum((w / 100) ** 2 for w in weights_before), 4)
    a.herfindahl_after = round(sum((w / 100) ** 2 for w in weights_after), 4)

    if a.proposed_weight_pct and a.proposed_weight_pct >= CONCENTRATION_WARN_PCT:
        a.flags.append(
            f"would be {a.proposed_weight_pct:.0f}% of the book — a single position that size "
            "drives the outcome more than the rest of your research does"
        )
    if a.rank_after == 1 and len(after_map) > 1:
        a.notes.append("this would become your largest position")

    # --- correlation and marginal risk -----------------------------------
    book, notes = _book_returns(holdings, data_service, days)
    a.notes.extend(notes)

    try:
        cand = _returns(data_service.get_price_history(ticker, days=days))
    except Exception as e:
        cand = None
        a.notes.append(f"no price history for {ticker}: {e}")

    if cand is not None and not cand.empty:
        a.candidate_volatility_pct = round(float(cand.std() * math.sqrt(TRADING_DAYS)) * 100, 2)

    if book is not None and cand is not None:
        joined = pd.concat([book.rename("book"), cand.rename("cand")], axis=1).dropna()
        a.overlap_observations = int(len(joined))
        if len(joined) >= MIN_OVERLAP:
            rho = _finite(joined["book"].corr(joined["cand"]))
            sig_p = _finite(joined["book"].std() * math.sqrt(TRADING_DAYS))
            sig_c = _finite(joined["cand"].std() * math.sqrt(TRADING_DAYS))
            a.correlation_to_book = None if rho is None else round(rho, 3)
            a.portfolio_volatility_before_pct = None if sig_p is None else round(sig_p * 100, 2)

            if None not in (rho, sig_p, sig_c) and denom > 0:
                w = max(0.0, min(1.0, new_value / denom))
                # Two-asset variance: the existing book and the enlarged position.
                var = (
                    (1 - w) ** 2 * sig_p**2
                    + w**2 * sig_c**2
                    + 2 * w * (1 - w) * sig_p * sig_c * rho
                )
                sig_after = math.sqrt(max(var, 0.0))
                a.portfolio_volatility_after_pct = round(sig_after * 100, 2)
                a.volatility_change_pct = round((sig_after - sig_p) * 100, 2)
                a.diversifying = bool(sig_after < sig_p)

            if rho is not None and rho >= HIGH_CORRELATION:
                a.flags.append(
                    f"moves with the existing book (correlation {rho:.2f}) — this is closer to "
                    "increasing your current exposure than to adding a new one"
                )
            elif rho is not None and rho < 0.3:
                a.notes.append(
                    f"low correlation to the book ({rho:.2f}); it diversifies as well as it performs"
                )
        else:
            a.notes.append(
                f"only {len(joined)} overlapping days with the book — too few to quote a correlation"
            )
    elif book is None:
        a.notes.append(
            "no existing holdings with price history, so there is nothing to compare against"
        )

    if a.volatility_change_pct is not None:
        direction = "raises" if a.volatility_change_pct > 0 else "lowers"
        a.notes.append(
            f"{direction} portfolio volatility by {abs(a.volatility_change_pct):.2f} "
            f"points to {a.portfolio_volatility_after_pct:.2f}%"
        )

    return a
