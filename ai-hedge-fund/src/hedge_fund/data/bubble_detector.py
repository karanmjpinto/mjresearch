"""Market-wide "bubble detector" — composite of macro valuation & complacency gauges.

Inspired by levels.io/bubble-detector. Each gauge is derived from FRED series and
scored against its own history (percentile + z-score) so units cancel and readings
are comparable. A gauge's ``risk_score`` is 0-100 where higher means more froth /
bubble risk; the composite is the mean of available gauge scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class GaugeSpec:
    id: str
    label: str
    description: str
    # "high" -> a high value signals more bubble risk (froth);
    # "low"  -> a low value signals more bubble risk (complacency / late-cycle).
    direction: str
    unit: str
    # Either a single FRED series id, or a numerator/denominator ratio.
    series: str | None = None
    numerator: str | None = None
    denominator: str | None = None


# Gauges that map cleanly to FRED series. CAPE and Tobin's Q are intentionally
# omitted — they lack a reliable single FRED source.
GAUGE_SPECS: tuple[GaugeSpec, ...] = (
    GaugeSpec(
        id="buffett_indicator",
        label="Buffett Indicator",
        description="US corporate equity market value (nonfinancial corporate "
        "equities) relative to GDP. Elevated readings mean stocks are richly "
        "valued versus the real economy.",
        direction="high",
        unit="ratio",
        numerator="NCBEILQ027S",
        denominator="GDP",
    ),
    GaugeSpec(
        id="sp500_to_m2",
        label="S&P 500 / M2",
        description="S&P 500 relative to the M2 money supply. Separates genuine "
        "gains from liquidity-driven inflation of asset prices.",
        direction="high",
        unit="ratio",
        numerator="SP500",
        denominator="M2SL",
    ),
    GaugeSpec(
        id="vix",
        label="VIX (complacency)",
        description="Equity volatility / fear index. Very low readings indicate "
        "the complacency typical of late-stage bubbles.",
        direction="low",
        unit="index",
        series="VIXCLS",
    ),
    GaugeSpec(
        id="high_yield_spread",
        label="High-Yield Credit Spread",
        description="ICE BofA US high-yield option-adjusted spread. Tight spreads "
        "mean lenders are underpricing risk.",
        direction="low",
        unit="pct",
        series="BAMLH0A0HYM2",
    ),
    GaugeSpec(
        id="yield_curve",
        label="Yield Curve (10y-2y)",
        description="Spread between 10-year and 2-year Treasuries. Inverted "
        "(negative) curves have historically preceded recessions.",
        direction="low",
        unit="pct",
        series="T10Y2Y",
    ),
)


def _status_from_score(score: float) -> str:
    if score >= 80:
        return "extreme"
    if score >= 60:
        return "elevated"
    if score >= 40:
        return "moderate"
    if score >= 20:
        return "low"
    return "minimal"


def _to_series(obj: Any) -> pd.Series | None:
    """Coerce a FRED result (DataFrame or Series) into a clean float Series."""
    if obj is None:
        return None
    if isinstance(obj, pd.DataFrame):
        if obj.empty:
            return None
        s = obj.iloc[:, 0]
    elif isinstance(obj, pd.Series):
        s = obj
    else:
        return None
    s = pd.to_numeric(s, errors="coerce").dropna()
    return s if not s.empty else None


def _gauge_series(spec: GaugeSpec, fred: dict[str, Any]) -> pd.Series | None:
    """Build the underlying series for a gauge (raw or aligned ratio)."""
    if spec.series is not None:
        return _to_series(fred.get(spec.series))

    num = _to_series(fred.get(spec.numerator))
    den = _to_series(fred.get(spec.denominator))
    if num is None or den is None:
        return None
    # Align on the union of dates and forward-fill (GDP/M2 are lower frequency).
    frame = pd.concat([num.rename("num"), den.rename("den")], axis=1).sort_index()
    frame = frame.ffill().dropna()
    if frame.empty:
        return None
    ratio = frame["num"] / frame["den"]
    return ratio.replace([float("inf"), float("-inf")], pd.NA).dropna()


def _score_gauge(spec: GaugeSpec, series: pd.Series) -> dict[str, Any] | None:
    if series is None or len(series) < 2:
        return None
    latest = float(series.iloc[-1])
    mean = float(series.mean())
    std = float(series.std())
    zscore = (latest - mean) / std if std > 0 else 0.0
    # Percentile of the latest value within its own history (0-100).
    percentile = float((series <= latest).mean() * 100.0)
    risk_score = percentile if spec.direction == "high" else 100.0 - percentile
    return {
        "id": spec.id,
        "label": spec.label,
        "description": spec.description,
        "direction": spec.direction,
        "unit": spec.unit,
        "value": round(latest, 4),
        "mean": round(mean, 4),
        "zscore": round(zscore, 2),
        "percentile": round(percentile, 1),
        "risk_score": round(risk_score, 1),
        "status": _status_from_score(risk_score),
        "as_of": str(series.index[-1].date())
        if hasattr(series.index[-1], "date")
        else str(series.index[-1]),
    }


def compute_bubble_detector(fred: dict[str, Any]) -> dict[str, Any]:
    """Compute the bubble detector from a map of FRED series id -> DataFrame/Series.

    Missing series are skipped gracefully; the composite averages whatever gauges
    could be computed.
    """
    gauges: list[dict[str, Any]] = []
    missing: list[str] = []
    for spec in GAUGE_SPECS:
        series = _gauge_series(spec, fred)
        scored = _score_gauge(spec, series)
        if scored is None:
            missing.append(spec.id)
        else:
            gauges.append(scored)

    if not gauges:
        return {"error": "no macro data available", "source": "FRED"}

    composite = round(sum(g["risk_score"] for g in gauges) / len(gauges), 1)
    as_of = max(g["as_of"] for g in gauges)
    return {
        "composite_score": composite,
        "composite_status": _status_from_score(composite),
        "gauges": gauges,
        "missing_gauges": missing,
        "as_of": as_of,
        "source": "FRED",
        "note": "risk_score is 0-100 (higher = more froth). Percentiles are vs. "
        "each gauge's own history in the requested window, not absolute thresholds.",
    }


# FRED series required to compute every gauge — used by the data service to fetch.
REQUIRED_SERIES: tuple[str, ...] = tuple(
    dict.fromkeys(  # de-dupe, preserve order
        sid
        for spec in GAUGE_SPECS
        for sid in ((spec.series,) if spec.series else (spec.numerator, spec.denominator))
        if sid is not None
    )
)
