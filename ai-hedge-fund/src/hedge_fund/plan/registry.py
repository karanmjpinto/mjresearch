"""The deterministic metrics a plan may compose.

Every number a research answer relies on is produced here, in ordinary Python,
from the snapshot and the price history. The model's job is to choose which of
these to run and to explain what the results mean — never to produce the results
itself. That division is the whole point: a chosen metric can be wrong, but it
cannot be invented, and a wrong choice is visible in the plan.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from hedge_fund.plan.types import FieldSpec, Metric, MetricError, ParamSpec

TRADING_DAYS = 252

_REGISTRY: dict[str, Metric] = {}


def register(metric: Metric) -> Metric:
    if metric.id in _REGISTRY:
        raise ValueError(f"duplicate metric id: {metric.id}")
    _REGISTRY[metric.id] = metric
    return metric


def get_metric(metric_id: str) -> Metric:
    try:
        return _REGISTRY[metric_id]
    except KeyError:
        raise MetricError(f"unknown metric: {metric_id}") from None


def all_metrics() -> list[Metric]:
    return sorted(_REGISTRY.values(), key=lambda m: (m.tier, m.id))


def catalog() -> list[dict[str, Any]]:
    """Every metric signature — this is what the planner model is shown."""
    return [m.signature() for m in all_metrics()]


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value: float | None, places: int = 4) -> float | None:
    return None if value is None else round(value, places)


def _require_close(ctx: Any, days: int) -> pd.Series:
    df = ctx.price_frame(days)
    if df is None or df.empty or "close" not in df:
        raise MetricError(f"no price history available for a {days}-day window")
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(close) < 3:
        raise MetricError(f"only {len(close)} usable price points for a {days}-day window")
    return close


def _snapshot_value(ctx: Any, *path: str) -> Any:
    node: Any = ctx.snapshot
    for part in path:
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


# ----------------------------------------------------------------------
# load tier
# ----------------------------------------------------------------------


def _price_window(ctx: Any, days: int) -> dict[str, Any]:
    close = _require_close(ctx, days)
    first, last = float(close.iloc[0]), float(close.iloc[-1])
    return {
        "observations": int(len(close)),
        "first_close": _round(first, 4),
        "last_close": _round(last, 4),
        "high": _round(float(close.max()), 4),
        "low": _round(float(close.min()), 4),
        "total_return_pct": _round((last / first - 1) * 100, 2),
        "window_start": str(close.index.min())[:10],
        "window_end": str(close.index.max())[:10],
    }


register(
    Metric(
        id="price_window",
        label="Price window",
        description=(
            "Summarize closing prices over a lookback window: first/last close, "
            "high, low, and total return across the window."
        ),
        tier="load",
        params=(
            ParamSpec(
                "days",
                "integer",
                "Calendar days of history to load. 30 is a month, 252 roughly a year.",
                default=90,
                minimum=5,
                maximum=3650,
            ),
        ),
        outputs=(
            FieldSpec("observations", "integer", "Number of usable closing prices in the window"),
            FieldSpec("first_close", "number", "Closing price on the first day of the window"),
            FieldSpec("last_close", "number", "Most recent closing price"),
            FieldSpec("high", "number", "Highest close in the window"),
            FieldSpec("low", "number", "Lowest close in the window"),
            FieldSpec("total_return_pct", "number", "Percent change first to last close", "%"),
            FieldSpec("window_start", "date", "First date covered"),
            FieldSpec("window_end", "date", "Last date covered"),
        ),
        fn=_price_window,
    )
)


def _fundamentals_snapshot(ctx: Any) -> dict[str, Any]:
    f = _snapshot_value(ctx, "fundamentals") or {}
    if f.get("error"):
        raise MetricError(f"fundamentals unavailable: {f['error']}")
    return {
        "pe_ratio": _num(f.get("pe_ratio")),
        "forward_pe": _num(f.get("forward_pe")),
        "price_to_book": _num(f.get("price_to_book")),
        "peg_ratio": _num(f.get("peg_ratio")),
        "market_cap": _num(f.get("market_cap")),
        "beta": _num(f.get("beta")),
        "currency": str(f.get("currency") or "") or None,
        "sector": str(f.get("sector") or "") or None,
    }


register(
    Metric(
        id="fundamentals",
        label="Fundamental metrics",
        description="Valuation multiples and descriptive fields from the snapshot.",
        tier="load",
        outputs=(
            FieldSpec("pe_ratio", "number", "Trailing price-to-earnings multiple", "x"),
            FieldSpec("forward_pe", "number", "Forward price-to-earnings multiple", "x"),
            FieldSpec("price_to_book", "number", "Price-to-book multiple", "x"),
            FieldSpec("peg_ratio", "number", "P/E divided by expected growth", "x"),
            FieldSpec("market_cap", "number", "Market capitalisation in the reporting currency"),
            FieldSpec("beta", "number", "Sensitivity to the broad market"),
            FieldSpec("currency", "string", "Reporting currency of the amounts above"),
            FieldSpec("sector", "string", "Sector classification"),
        ),
        fn=_fundamentals_snapshot,
        notes="Values may be null when the provider did not supply them.",
    )
)


def _technicals_snapshot(ctx: Any) -> dict[str, Any]:
    t = _snapshot_value(ctx, "technicals") or {}
    if t.get("error"):
        raise MetricError(f"technicals unavailable: {t['error']}")
    return {
        "rsi_14": _num(t.get("rsi_14")),
        "sma_50": _num(t.get("sma_50")),
        "sma_200": _num(t.get("sma_200")),
        "atr_14": _num(t.get("atr_14")),
        "price": _num(t.get("price")),
    }


register(
    Metric(
        id="technicals",
        label="Technical indicators",
        description="Pre-computed indicators from the snapshot: RSI, moving averages, ATR.",
        tier="load",
        outputs=(
            FieldSpec("rsi_14", "number", "14-period relative strength index, 0-100"),
            FieldSpec("sma_50", "number", "50-day simple moving average"),
            FieldSpec("sma_200", "number", "200-day simple moving average"),
            FieldSpec("atr_14", "number", "14-period average true range"),
            FieldSpec("price", "number", "Price the indicators were computed against"),
        ),
        fn=_technicals_snapshot,
    )
)


# ----------------------------------------------------------------------
# transform tier
# ----------------------------------------------------------------------


def _return_stats(ctx: Any, days: int, rf_annual: float) -> dict[str, Any]:
    close = _require_close(ctx, days)
    rets = close.pct_change().dropna()
    if len(rets) < 2:
        raise MetricError("not enough returns to compute statistics")

    total = float(close.iloc[-1] / close.iloc[0] - 1)
    years = len(close) / TRADING_DAYS
    cagr = float((close.iloc[-1] / close.iloc[0]) ** (1 / years) - 1) if years > 0 else 0.0
    vol = float(rets.std() * math.sqrt(TRADING_DAYS))
    rf_per_bar = (1 + rf_annual) ** (1 / TRADING_DAYS) - 1
    excess = rets - rf_per_bar
    sharpe = float(excess.mean() / rets.std() * math.sqrt(TRADING_DAYS)) if rets.std() > 0 else 0.0
    downside = rets[rets < 0]
    sortino = (
        float(excess.mean() / downside.std() * math.sqrt(TRADING_DAYS))
        if len(downside) > 1 and downside.std() > 0
        else 0.0
    )
    return {
        "total_return_pct": _round(total * 100, 2),
        "annualized_return_pct": _round(cagr * 100, 2),
        "annualized_volatility_pct": _round(vol * 100, 2),
        "sharpe_ratio": _round(sharpe, 3),
        "sortino_ratio": _round(sortino, 3),
        "positive_day_pct": _round(float((rets > 0).mean() * 100), 2),
    }


register(
    Metric(
        id="return_stats",
        label="Return statistics",
        description=(
            "Risk and return over a window: annualized return, volatility, "
            "Sharpe and Sortino ratios, and the share of up days."
        ),
        tier="transform",
        params=(
            ParamSpec(
                "days",
                "integer",
                "Lookback window in calendar days.",
                default=365,
                minimum=30,
                maximum=3650,
            ),
            ParamSpec(
                "rf_annual",
                "number",
                "Annual risk-free rate as a decimal (0.04 = 4%). Affects Sharpe and Sortino.",
                default=0.04,
                minimum=0.0,
                maximum=0.25,
            ),
        ),
        outputs=(
            FieldSpec("total_return_pct", "number", "Return across the whole window", "%"),
            FieldSpec("annualized_return_pct", "number", "Compound annual growth rate", "%"),
            FieldSpec("annualized_volatility_pct", "number", "Annualized standard deviation", "%"),
            FieldSpec("sharpe_ratio", "number", "Excess return per unit of total volatility"),
            FieldSpec("sortino_ratio", "number", "Excess return per unit of downside volatility"),
            FieldSpec("positive_day_pct", "number", "Share of days with a positive return", "%"),
        ),
        fn=_return_stats,
    )
)


def _drawdown_profile(ctx: Any, days: int) -> dict[str, Any]:
    close = _require_close(ctx, days)
    running_max = close.cummax()
    dd = (close - running_max) / running_max
    max_dd = float(dd.min())
    trough_idx = dd.idxmin()
    peak_before = close.loc[:trough_idx].idxmax()
    recovered = bool(close.iloc[-1] >= close.loc[peak_before])
    return {
        "max_drawdown_pct": _round(max_dd * 100, 2),
        "current_drawdown_pct": _round(float(dd.iloc[-1]) * 100, 2),
        "trough_date": str(trough_idx)[:10],
        "peak_date": str(peak_before)[:10],
        "recovered": recovered,
    }


register(
    Metric(
        id="drawdown_profile",
        label="Drawdown profile",
        description="Worst peak-to-trough decline in the window, and whether it has recovered.",
        tier="transform",
        params=(
            ParamSpec(
                "days",
                "integer",
                "Lookback window in calendar days.",
                default=365,
                minimum=30,
                maximum=3650,
            ),
        ),
        outputs=(
            FieldSpec(
                "max_drawdown_pct", "number", "Largest peak-to-trough decline, negative", "%"
            ),
            FieldSpec("current_drawdown_pct", "number", "Decline from the running peak today", "%"),
            FieldSpec("trough_date", "date", "Date of the lowest point"),
            FieldSpec("peak_date", "date", "Date of the peak preceding the trough"),
            FieldSpec("recovered", "boolean", "Whether price has regained the prior peak"),
        ),
        fn=_drawdown_profile,
    )
)


def _moving_average_state(ctx: Any) -> dict[str, Any]:
    t = _snapshot_value(ctx, "technicals") or {}
    price = _num(t.get("price")) or _num(_snapshot_value(ctx, "price", "current"))
    sma50, sma200 = _num(t.get("sma_50")), _num(t.get("sma_200"))
    if price is None or (sma50 is None and sma200 is None):
        raise MetricError("moving averages unavailable in the snapshot")

    def gap(ma: float | None) -> float | None:
        return None if ma in (None, 0) else _round((price / ma - 1) * 100, 2)

    trend = "unknown"
    if sma50 is not None and sma200 is not None:
        trend = "uptrend" if sma50 > sma200 else "downtrend"
    return {
        "above_sma_50": None if sma50 is None else bool(price > sma50),
        "above_sma_200": None if sma200 is None else bool(price > sma200),
        "gap_to_sma_50_pct": gap(sma50),
        "gap_to_sma_200_pct": gap(sma200),
        "golden_cross": trend == "uptrend",
        "trend_label": trend,
    }


register(
    Metric(
        id="moving_average_state",
        label="Moving average state",
        description="Where price sits relative to its 50- and 200-day moving averages.",
        tier="transform",
        outputs=(
            FieldSpec("above_sma_50", "boolean", "Price is above the 50-day average"),
            FieldSpec("above_sma_200", "boolean", "Price is above the 200-day average"),
            FieldSpec("gap_to_sma_50_pct", "number", "Percent above/below the 50-day average", "%"),
            FieldSpec(
                "gap_to_sma_200_pct", "number", "Percent above/below the 200-day average", "%"
            ),
            FieldSpec("golden_cross", "boolean", "50-day average is above the 200-day average"),
            FieldSpec("trend_label", "string", "uptrend, downtrend, or unknown"),
        ),
        fn=_moving_average_state,
    )
)


def _range_position(ctx: Any) -> dict[str, Any]:
    f = _snapshot_value(ctx, "fundamentals") or {}
    price = _num(_snapshot_value(ctx, "price", "current"))
    high, low = _num(f.get("52w_high")), _num(f.get("52w_low"))
    if price is None or high is None or low is None or high <= low:
        raise MetricError("52-week range unavailable in the snapshot")
    pct = (price - low) / (high - low) * 100
    return {
        "range_position_pct": _round(pct, 2),
        "pct_below_52w_high": _round((price / high - 1) * 100, 2),
        "pct_above_52w_low": _round((price / low - 1) * 100, 2),
        "near_high": bool(pct >= 90),
        "near_low": bool(pct <= 10),
    }


register(
    Metric(
        id="range_position",
        label="52-week range position",
        description="Where the current price sits inside its 52-week high-low range.",
        tier="transform",
        outputs=(
            FieldSpec("range_position_pct", "number", "0 = at the 52w low, 100 = at the high", "%"),
            FieldSpec("pct_below_52w_high", "number", "Distance below the 52-week high", "%"),
            FieldSpec("pct_above_52w_low", "number", "Distance above the 52-week low", "%"),
            FieldSpec("near_high", "boolean", "Within 10% of the top of the range"),
            FieldSpec("near_low", "boolean", "Within 10% of the bottom of the range"),
        ),
        fn=_range_position,
    )
)


def _momentum(ctx: Any, lookback_days: int, skip_days: int) -> dict[str, Any]:
    close = _require_close(ctx, lookback_days + skip_days + 10)
    if skip_days > 0:
        if len(close) <= skip_days + 2:
            raise MetricError("not enough history to skip the most recent period")
        close = close.iloc[:-skip_days]
    if len(close) < 3:
        raise MetricError("not enough history for a momentum reading")
    first, last = float(close.iloc[0]), float(close.iloc[-1])
    return {
        "momentum_pct": _round((last / first - 1) * 100, 2),
        "measured_from": str(close.index.min())[:10],
        "measured_to": str(close.index.max())[:10],
        "skipped_days": skip_days,
    }


register(
    Metric(
        id="momentum",
        label="Price momentum",
        description=(
            "Trailing price momentum, optionally skipping the most recent days to "
            "avoid the short-term reversal effect."
        ),
        tier="transform",
        params=(
            ParamSpec(
                "lookback_days",
                "integer",
                "Length of the momentum window in calendar days.",
                default=252,
                minimum=20,
                maximum=1825,
            ),
            ParamSpec(
                "skip_days",
                "integer",
                "Most recent days to exclude. 21 (one month) is the academic convention.",
                default=0,
                minimum=0,
                maximum=90,
            ),
        ),
        outputs=(
            FieldSpec("momentum_pct", "number", "Price change over the measured window", "%"),
            FieldSpec("measured_from", "date", "Start of the measured window"),
            FieldSpec("measured_to", "date", "End of the measured window"),
            FieldSpec("skipped_days", "integer", "Days excluded at the recent end"),
        ),
        fn=_momentum,
    )
)


def _volatility_regime(ctx: Any, short_days: int, long_days: int) -> dict[str, Any]:
    if short_days >= long_days:
        raise MetricError("short_days must be less than long_days")
    long_close = _require_close(ctx, long_days)
    rets = long_close.pct_change().dropna()
    if len(rets) < short_days + 5:
        raise MetricError("not enough history to compare volatility regimes")
    recent = rets.iloc[-short_days:]
    short_vol = float(recent.std() * math.sqrt(TRADING_DAYS)) * 100
    long_vol = float(rets.std() * math.sqrt(TRADING_DAYS)) * 100
    ratio = short_vol / long_vol if long_vol > 0 else None
    label = "unknown"
    if ratio is not None:
        label = "elevated" if ratio >= 1.25 else "subdued" if ratio <= 0.8 else "normal"
    return {
        "recent_volatility_pct": _round(short_vol, 2),
        "baseline_volatility_pct": _round(long_vol, 2),
        "volatility_ratio": _round(ratio, 3),
        "regime": label,
    }


register(
    Metric(
        id="volatility_regime",
        label="Volatility regime",
        description="Recent realised volatility against a longer baseline.",
        tier="transform",
        params=(
            ParamSpec(
                "short_days",
                "integer",
                "Recent window in trading days.",
                default=21,
                minimum=5,
                maximum=120,
            ),
            ParamSpec(
                "long_days",
                "integer",
                "Baseline window in calendar days.",
                default=365,
                minimum=60,
                maximum=3650,
            ),
        ),
        outputs=(
            FieldSpec(
                "recent_volatility_pct", "number", "Annualized volatility, recent window", "%"
            ),
            FieldSpec("baseline_volatility_pct", "number", "Annualized volatility, baseline", "%"),
            FieldSpec("volatility_ratio", "number", "Recent divided by baseline volatility"),
            FieldSpec("regime", "string", "elevated, normal, subdued, or unknown"),
        ),
        fn=_volatility_regime,
    )
)


def _news_sentiment_summary(ctx: Any) -> dict[str, Any]:
    ns = _snapshot_value(ctx, "news_sentiment") or {}
    if not ns.get("enabled"):
        raise MetricError("news sentiment scoring is not enabled in this snapshot")
    agg = ns.get("aggregate") or {}
    count = int(agg.get("article_count") or 0)
    if count == 0:
        raise MetricError("no scored articles in this snapshot")
    mean_signed = _num(agg.get("mean_signed"))
    label = "neutral"
    if mean_signed is not None:
        label = "positive" if mean_signed > 0.2 else "negative" if mean_signed < -0.2 else "neutral"
    return {
        "article_count": count,
        "mean_signed": _round(mean_signed, 4),
        "label": label,
    }


register(
    Metric(
        id="news_sentiment",
        label="News sentiment",
        description="Aggregate FinBERT sentiment across the headlines in the snapshot.",
        tier="transform",
        outputs=(
            FieldSpec("article_count", "integer", "Headlines that were scored"),
            FieldSpec("mean_signed", "number", "Mean sentiment, -1 (negative) to +1 (positive)"),
            FieldSpec("label", "string", "positive, neutral, or negative"),
        ),
        fn=_news_sentiment_summary,
        notes="Headline sentiment is noisy; treat it as a weak signal.",
    )
)


# ----------------------------------------------------------------------
# evaluate tier
# ----------------------------------------------------------------------


def _score_band(value: float | None, bands: list[tuple[float, int]], default: int = 50) -> int:
    """Map a value onto a 0-100 score using ordered (threshold, score) bands."""
    if value is None:
        return default
    for threshold, score in bands:
        if value <= threshold:
            return score
    return bands[-1][1] if bands else default


def _valuation_score(ctx: Any) -> dict[str, Any]:
    f = _snapshot_value(ctx, "fundamentals") or {}
    pe, pb, peg = _num(f.get("pe_ratio")), _num(f.get("price_to_book")), _num(f.get("peg_ratio"))
    if pe is None and pb is None and peg is None:
        raise MetricError("no valuation multiples available")

    components: list[int] = []
    used: list[str] = []
    if pe is not None and pe > 0:
        components.append(
            _score_band(pe, [(10, 90), (15, 78), (20, 65), (30, 48), (45, 30), (70, 15)], 8)
        )
        used.append("pe_ratio")
    if pb is not None and pb > 0:
        components.append(_score_band(pb, [(1, 90), (2, 75), (4, 58), (8, 40), (15, 22)], 10))
        used.append("price_to_book")
    if peg is not None and peg > 0:
        components.append(_score_band(peg, [(0.8, 88), (1.2, 72), (2.0, 52), (3.0, 32)], 15))
        used.append("peg_ratio")

    score = int(round(sum(components) / len(components)))
    return {
        "valuation_score": score,
        "label": "cheap" if score >= 65 else "expensive" if score <= 35 else "fair",
        "inputs_used": ", ".join(used),
        "input_count": len(components),
    }


register(
    Metric(
        id="valuation_score",
        label="Valuation score",
        description=(
            "Composite 0-100 valuation reading from the available multiples, where "
            "100 is cheapest. Uses whichever of P/E, P/B and PEG are present."
        ),
        tier="evaluate",
        outputs=(
            FieldSpec("valuation_score", "integer", "0 = very expensive, 100 = very cheap"),
            FieldSpec("label", "string", "cheap, fair, or expensive"),
            FieldSpec("inputs_used", "string", "Which multiples contributed"),
            FieldSpec("input_count", "integer", "How many multiples contributed"),
        ),
        fn=_valuation_score,
        notes="Absolute bands, not sector-relative. A low score is not by itself a sell.",
    )
)


def _risk_flags(ctx: Any) -> dict[str, Any]:
    flags: list[str] = []
    f = _snapshot_value(ctx, "fundamentals") or {}
    t = _snapshot_value(ctx, "technicals") or {}

    beta = _num(f.get("beta"))
    if beta is not None and beta > 1.5:
        flags.append("high beta (>1.5) — amplifies market moves")
    pe = _num(f.get("pe_ratio"))
    if pe is not None and pe > 50:
        flags.append("P/E above 50 — priced for sustained high growth")
    rsi = _num(t.get("rsi_14"))
    if rsi is not None and rsi > 75:
        flags.append("RSI above 75 — technically overbought")
    if rsi is not None and rsi < 25:
        flags.append("RSI below 25 — technically oversold")

    quality = _snapshot_value(ctx, "provenance", "warnings") or []
    if quality:
        flags.append(f"{len(quality)} data-quality warning(s) on this snapshot")

    return {
        "flags": "; ".join(flags) if flags else "none",
        "flag_count": len(flags),
        "has_data_quality_concern": bool(quality),
    }


register(
    Metric(
        id="risk_flags",
        label="Risk flags",
        description="Mechanical risk checks over the snapshot, including data-quality concerns.",
        tier="evaluate",
        outputs=(
            FieldSpec("flags", "string", "Semicolon-separated risk flags, or 'none'"),
            FieldSpec("flag_count", "integer", "How many flags fired"),
            FieldSpec(
                "has_data_quality_concern",
                "boolean",
                "Whether the underlying data carried verification warnings",
            ),
        ),
        fn=_risk_flags,
    )
)


def _weighted_conviction(
    ctx: Any,
    valuation_weight: float,
    momentum_weight: float,
    quality_weight: float,
    sentiment_weight: float,
) -> dict[str, Any]:
    """Combine already-computed dimension scores with explicit, auditable weights."""
    facts = ctx.facts
    weights = {
        "valuation": valuation_weight,
        "momentum": momentum_weight,
        "quality": quality_weight,
        "sentiment": sentiment_weight,
    }

    dims: dict[str, float] = {}
    if (v := facts.get("valuation_score")) is not None:
        dims["valuation"] = float(v)
    if (m := facts.get("momentum_pct")) is not None:
        # Map -50%..+50% onto 0..100, saturating outside that band.
        dims["momentum"] = max(0.0, min(100.0, 50.0 + float(m)))
    if (s := facts.get("sharpe_ratio")) is not None:
        dims["quality"] = max(0.0, min(100.0, 50.0 + float(s) * 25.0))
    if (n := facts.get("mean_signed")) is not None:
        dims["sentiment"] = max(0.0, min(100.0, 50.0 + float(n) * 50.0))

    if not dims:
        raise MetricError(
            "no dimension scores available — run valuation_score, momentum, "
            "return_stats or news_sentiment first"
        )

    total_weight = sum(weights[k] for k in dims)
    if total_weight <= 0:
        raise MetricError("all weights for the available dimensions are zero")
    score = sum(dims[k] * weights[k] for k in dims) / total_weight

    return {
        "conviction_score": int(round(max(0.0, min(100.0, score)))),
        "dimensions_used": ", ".join(sorted(dims)),
        "dimension_count": len(dims),
        "effective_weight": _round(total_weight, 3),
    }


register(
    Metric(
        id="weighted_conviction",
        label="Weighted conviction",
        description=(
            "Combine the dimension scores already computed in this plan into a single "
            "0-100 conviction using explicit weights. Dimensions that were not "
            "computed are excluded and the remaining weights are renormalised, so the "
            "number is always reproducible from the plan alone."
        ),
        tier="evaluate",
        params=(
            ParamSpec(
                "valuation_weight",
                "number",
                "Weight on the valuation score.",
                default=1.0,
                minimum=0.0,
                maximum=10.0,
            ),
            ParamSpec(
                "momentum_weight",
                "number",
                "Weight on price momentum.",
                default=1.0,
                minimum=0.0,
                maximum=10.0,
            ),
            ParamSpec(
                "quality_weight",
                "number",
                "Weight on risk-adjusted return (Sharpe).",
                default=1.0,
                minimum=0.0,
                maximum=10.0,
            ),
            ParamSpec(
                "sentiment_weight",
                "number",
                "Weight on news sentiment.",
                default=0.5,
                minimum=0.0,
                maximum=10.0,
            ),
        ),
        outputs=(
            FieldSpec(
                "conviction_score", "integer", "0 = strong sell, 50 = neutral, 100 = strong buy"
            ),
            FieldSpec("dimensions_used", "string", "Which dimensions contributed"),
            FieldSpec("dimension_count", "integer", "How many dimensions contributed"),
            FieldSpec("effective_weight", "number", "Sum of weights actually applied"),
        ),
        fn=_weighted_conviction,
        consumes=("valuation_score", "momentum", "return_stats", "news_sentiment"),
        notes="Run after the dimension metrics it depends on; it reads their outputs.",
    )
)
