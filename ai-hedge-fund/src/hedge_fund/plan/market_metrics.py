"""Metrics that compare the stock with something outside it: a macro factor or
its peers.

These are the questions a single company's numbers cannot answer — how much
does it move with the gas price, what happened to it after rate shocks, is it
cheap against Microsoft — and the ones Bridgewater built PAT around: its
showcase was an event study of asset moves after oil shocks.

`FACTORS` is the macro catalog the planner may name. Each factor records its
FRED id, its unit, and how a move in it is measured, because that choice is the
whole meaning of a beta: a yield moves in points and is differenced, a price
moves in percent and is compounded. Mixing them gives a number with no unit.

Both kinds of data are fetched at execution time through the data service, as
price history already is, and cut at the snapshot's as-of date.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any

import pandas as pd

from hedge_fund.plan.registry import _require_close, _round, register
from hedge_fund.plan.types import FieldSpec, Metric, MetricError, ParamSpec


@dataclass(frozen=True)
class Factor:
    id: str
    fred: str
    label: str
    kind: str  # "rate": changes in points; "price": percent changes
    unit_of_move: str


FACTORS: dict[str, Factor] = {
    f.id: f
    for f in (
        # Units in words: a digit here was read back out of the prose as a value.
        Factor("rates_10y", "DGS10", "US 10-year Treasury yield", "rate", "one percentage point"),
        Factor(
            "natural_gas", "DHHNGSP", "Henry Hub natural gas price", "price", "a ten percent move"
        ),
        Factor("oil_wti", "DCOILWTICO", "WTI crude oil price", "price", "a ten percent move"),
        Factor("us_dollar", "DTWEXBGS", "Broad US dollar index", "price", "a ten percent move"),
    )
}

#: Weeks, not days: daily closes of a stock and a FRED series are stamped on
#: different calendars and holidays, and a one-day misalignment is half the
#: signal in a daily regression.
WEEK = "W-FRI"


def _factor(name: str) -> Factor:
    try:
        return FACTORS[name]
    except KeyError:
        raise MetricError(
            f"unknown factor {name!r}; choose one of {', '.join(sorted(FACTORS))}"
        ) from None


def _weekly_moves(ctx: Any, factor: Factor, days: int) -> pd.DataFrame:
    """Aligned weekly stock returns (%) and factor moves, in the factor's unit."""
    close = _require_close(ctx, days)
    close.index = pd.to_datetime(close.index).tz_localize(None)
    stock = close.resample(WEEK).last().pct_change() * 100
    level = ctx.macro_series(factor.fred, days).resample(WEEK).last()
    # Per-unit scaling so the beta reads "stock % per one unit_of_move".
    move = level.diff() if factor.kind == "rate" else level.pct_change() * 10
    both = pd.concat({"stock": stock, "factor": move}, axis=1).dropna()
    if len(both) < 26:
        raise MetricError(f"only {len(both)} aligned weeks; at least 26 are needed")
    return both


def _macro_sensitivity(ctx: Any, factor: str, days: int) -> dict[str, Any]:
    f = _factor(factor)
    both = _weekly_moves(ctx, f, days)
    x, y = both["factor"].tolist(), both["stock"].tolist()
    if statistics.pvariance(x) == 0:
        raise MetricError(f"{f.label} did not move in the window")
    beta = statistics.covariance(x, y) / statistics.variance(x)
    corr = statistics.correlation(x, y)
    return {
        "factor_label": f.label,
        "factor_beta_pct": _round(beta, 3),
        "factor_correlation": _round(corr, 3),
        "factor_r_squared": _round(corr * corr, 3),
        "factor_move_unit": f.unit_of_move,
        "factor_weeks_used": len(both),
    }


register(
    Metric(
        id="macro_sensitivity",
        label="Macro sensitivity",
        description="How much the stock moves with a macro factor — rates, natural gas, oil or "
        "the dollar: its weekly beta to the factor, the correlation, and how much of its "
        "movement the factor explains.",
        tier="transform",
        params=(
            ParamSpec(
                "factor",
                "string",
                "The macro factor.",
                required=True,
                choices=tuple(sorted(FACTORS)),
            ),
            ParamSpec(
                "days",
                "integer",
                "Lookback window in calendar days.",
                default=730,
                minimum=270,
                maximum=3650,
            ),
        ),
        outputs=(
            FieldSpec("factor_label", "string", "The factor measured"),
            FieldSpec(
                "factor_beta_pct",
                "number",
                "Average weekly stock move, in percent, per factor_move_unit of the factor",
            ),
            FieldSpec("factor_correlation", "number", "Correlation of weekly moves, -1 to 1"),
            FieldSpec(
                "factor_r_squared", "number", "Share of weekly stock variance the factor explains"
            ),
            FieldSpec("factor_move_unit", "string", "The factor move the beta is per"),
            FieldSpec("factor_weeks_used", "integer", "Aligned weeks in the regression"),
        ),
        notes="A beta is a historical average, not a forecast, and says nothing about cause.",
        fn=_macro_sensitivity,
    )
)


def _event_study(ctx: Any, factor: str, sigma: float, days: int) -> dict[str, Any]:
    f = _factor(factor)
    both = _weekly_moves(ctx, f, days)
    sd = statistics.pstdev(both["factor"])
    if sd == 0:
        raise MetricError(f"{f.label} did not move in the window")
    # The stock's return in the week AFTER a shock week, so the shock is known
    # before the return is measured.
    after = both["stock"].shift(-1)
    up = after[both["factor"] >= sigma * sd].dropna()
    down = after[both["factor"] <= -sigma * sd].dropna()
    if len(up) + len(down) == 0:
        raise MetricError(f"no {f.label} move of {sigma} standard deviations in the window")

    def mean(s: pd.Series) -> float | None:
        return _round(float(s.mean()), 2) if len(s) else None

    return {
        "shock_weeks_up": int(len(up)),
        "shock_weeks_down": int(len(down)),
        "return_week_after_up_pct": mean(up),
        "return_week_after_down_pct": mean(down),
        "return_any_week_pct": _round(float(both["stock"].mean()), 2),
        "shock_threshold": _round(sigma * sd, 3),
        "shock_factor_label": f.label,
        "event_weeks_used": len(both),
    }


register(
    Metric(
        id="event_study",
        label="Event study",
        description="What the stock did in the week after unusually large moves in a macro "
        "factor, up and down, against an ordinary week.",
        tier="transform",
        params=(
            ParamSpec(
                "factor",
                "string",
                "The macro factor.",
                required=True,
                choices=tuple(sorted(FACTORS)),
            ),
            ParamSpec(
                "sigma",
                "number",
                "How many standard deviations counts as a shock.",
                default=2.0,
                minimum=1.0,
                maximum=4.0,
            ),
            ParamSpec(
                "days",
                "integer",
                "Lookback window in calendar days.",
                default=1825,
                minimum=365,
                maximum=3650,
            ),
        ),
        outputs=(
            FieldSpec(
                "shock_weeks_up", "integer", "Weeks the factor rose by the threshold or more"
            ),
            FieldSpec(
                "shock_weeks_down", "integer", "Weeks the factor fell by the threshold or more"
            ),
            FieldSpec(
                "return_week_after_up_pct",
                "number",
                "Average stock return the week after a rise",
                "%",
            ),
            FieldSpec(
                "return_week_after_down_pct",
                "number",
                "Average stock return the week after a fall",
                "%",
            ),
            FieldSpec(
                "return_any_week_pct",
                "number",
                "Average stock return in any week, for comparison",
                "%",
            ),
            FieldSpec(
                "shock_threshold",
                "number",
                "The factor move that counted as a shock, in its own unit",
            ),
            FieldSpec("shock_factor_label", "string", "The factor studied"),
            FieldSpec("event_weeks_used", "integer", "Weeks in the window studied"),
        ),
        notes="A handful of shock weeks is anecdote, not evidence; read the counts first.",
        fn=_event_study,
    )
)


_MULTIPLES = (("pe_ratio", "pe"), ("forward_pe", "forward_pe"), ("price_to_book", "price_to_book"))


def _peer_comparison(ctx: Any, peers: str) -> dict[str, Any]:
    named = [p.strip().upper() for p in peers.split(",") if p.strip()] if peers else None
    table = ctx.peer_metrics(named)
    me = table.get(ctx.ticker) or {}
    # Another share class of the same company is not a peer: the TAP peer set
    # included TAP-A, which pulls the "peer median" toward the company itself.
    root = ctx.ticker.split("-")[0].split(".")[0]
    others = {k: v for k, v in table.items() if k.split("-")[0].split(".")[0] != root}
    if not others:
        raise MetricError("no peers found")
    out: dict[str, Any] = {"peers_compared": ", ".join(sorted(others)), "peer_count": len(others)}
    for field, short in _MULTIPLES:
        vals = [
            float(v[field])
            for v in others.values()
            if isinstance(v.get(field), (int, float)) and math.isfinite(v[field]) and v[field] > 0
        ]
        med = statistics.median(vals) if vals else None
        mine = me.get(field)
        mine = float(mine) if isinstance(mine, (int, float)) and mine > 0 else None
        out[f"peer_median_{short}"] = _round(med, 2)
        out[f"{short}_vs_peer_median_pct"] = (
            _round((mine / med - 1) * 100, 1) if mine is not None and med else None
        )
    return out


register(
    Metric(
        id="peer_comparison",
        label="Peer comparison",
        description="The company's P/E, forward P/E and price-to-book against the median of its "
        "peers — the data layer's peer set, or companies you name.",
        tier="transform",
        params=(
            ParamSpec(
                "peers",
                "string",
                "Comma-separated tickers to compare with, e.g. 'MSFT,GOOGL'. "
                "Empty uses the standard peer set.",
                default="",
            ),
        ),
        outputs=(
            FieldSpec("peers_compared", "string", "The peer tickers used"),
            FieldSpec("peer_count", "integer", "How many peers had data"),
            FieldSpec("peer_median_pe", "number", "Median trailing P/E of the peers"),
            FieldSpec(
                "pe_vs_peer_median_pct",
                "number",
                "The company's P/E above (+) or below (-) the peer median",
                "%",
            ),
            FieldSpec("peer_median_forward_pe", "number", "Median forward P/E of the peers"),
            FieldSpec(
                "forward_pe_vs_peer_median_pct",
                "number",
                "The company's forward P/E against the peer median",
                "%",
            ),
            FieldSpec("peer_median_price_to_book", "number", "Median price-to-book of the peers"),
            FieldSpec(
                "price_to_book_vs_peer_median_pct",
                "number",
                "The company's price-to-book against the peer median",
                "%",
            ),
        ),
        notes="Peer multiples are fetched live, so they can differ from the snapshot's date.",
        fn=_peer_comparison,
    )
)
