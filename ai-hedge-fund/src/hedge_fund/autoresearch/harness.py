"""The evaluation harness. Fixed ground truth the search cannot modify.

Ported from the shape of karpathy/autoresearch: a baseline is established
first, every experiment runs against an identical fixed budget, one metric
decides, and the harness that computes it is off-limits to the thing being
optimised. Those constraints are what make a pile of overnight runs comparable
instead of a pile of anecdotes.

One thing does not transfer, and it is the whole difficulty. In LLM training a
held-out set keeps you honest: a change that only helps train loss shows up
immediately. Searching trading strategies over one price history has no such
safety net — run enough variants against the same past and something will look
excellent purely by chance. That is not a bug in the search, it is what search
does to a fixed sample.

So this harness does two things that the original does not need:

* **Splits time.** Hypotheses are formed and fitted on an in-sample window; the
  verdict comes from a later out-of-sample window the searcher never sees. A
  strategy that wins in-sample and collapses out-of-sample is a discovery about
  overfitting, not about markets, and it is recorded as such.
* **Counts the trials.** The more variants tried, the higher the bar the best
  one must clear to mean anything. The hurdle rises with the number of
  experiments, so the hundredth idea is not judged like the first.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from hedge_fund.quant.backtest import STRATEGY_META, run_backtest

# Fixed across every experiment. Changing these invalidates comparison against
# any result already recorded, which is why they live here and not in a request.
FEE_PCT = 0.0005
RF_ANNUAL = 0.04
MIN_OBSERVATIONS = 180
# Share of history reserved for the verdict. The searcher sees only the rest.
OUT_OF_SAMPLE_FRACTION = 0.3

# Primary metric. Lower Sharpe is worse; everything else is diagnostic.
PRIMARY_METRIC = "sharpe_ratio"


class HarnessError(Exception):
    """The experiment could not be evaluated. Not a verdict — an absence of one."""


@dataclass
class WindowResult:
    """Metrics for one time window."""

    label: str
    start: str
    end: str
    observations: int
    total_return_pct: float | None = None
    annualized_return_pct: float | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    max_drawdown_pct: float | None = None
    win_rate_pct: float | None = None
    trades: int | None = None
    time_in_market_pct: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Evaluation:
    """One hypothesis, evaluated in and out of sample."""

    ticker: str
    strategy_id: str
    params: dict[str, Any]
    in_sample: dict[str, Any]
    out_of_sample: dict[str, Any]
    baseline_out_of_sample: dict[str, Any] | None = None
    edge_vs_baseline: float | None = None
    degradation: float | None = None
    overfit_flag: bool = False
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _as_pct(value: Any) -> float | None:
    """The backtest engine reports fractions; these fields are percentages.

    Without the conversion a 99.8% time-in-market reads as 0.998% and trips the
    'barely in the market' check, and every return figure is off by 100x.
    """
    num = _num(value)
    return None if num is None else round(num * 100, 4)


def _window_result(label: str, frame: pd.DataFrame, result: Any) -> WindowResult:
    m = result.metrics if hasattr(result, "metrics") else (result or {})
    return WindowResult(
        label=label,
        start=str(frame.index.min())[:10],
        end=str(frame.index.max())[:10],
        observations=int(len(frame)),
        total_return_pct=_as_pct(m.get("total_return")),
        annualized_return_pct=_as_pct(m.get("cagr")),
        sharpe_ratio=_num(m.get("sharpe")),
        sortino_ratio=_num(m.get("sortino")),
        max_drawdown_pct=_as_pct(m.get("max_drawdown")),
        win_rate_pct=_as_pct(m.get("win_rate")),
        trades=int(_num(m.get("num_trades")) or 0),
        time_in_market_pct=_as_pct(m.get("time_in_market")),
    )


def split_history(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split chronologically. Never randomly — that leaks the future backwards."""
    if df is None or df.empty or "close" not in df:
        raise HarnessError("no price history")
    frame = df.sort_index()
    if len(frame) < MIN_OBSERVATIONS:
        raise HarnessError(
            f"only {len(frame)} observations; need {MIN_OBSERVATIONS} to split a window"
        )
    cut = int(len(frame) * (1 - OUT_OF_SAMPLE_FRACTION))
    return frame.iloc[:cut], frame.iloc[cut:]


def trials_adjusted_hurdle(n_trials: int, n_observations: int, base_sharpe: float = 0.0) -> float:
    """The Sharpe a *best-of-N* search must clear to mean anything.

    Search maximises noise as readily as signal. Under the null of no skill, the
    best of N independent trials still has an expected Sharpe above zero, and it
    grows with N — so the bar has to grow too, or the hundredth idea gets judged
    like the first.

    Uses the expected maximum of N standard normals, scaled by the standard
    error of a Sharpe estimate over the sample. This is the intuition behind
    Bailey and López de Prado's deflated Sharpe, kept deliberately simple; it is
    a sanity threshold, not a significance test.
    """
    trials = max(1, int(n_trials))
    obs = max(2, int(n_observations))
    # Standard error of an estimated Sharpe over `obs` observations.
    se = math.sqrt((1 + 0.5 * base_sharpe**2) / obs) * math.sqrt(252)
    if trials == 1:
        return base_sharpe
    # Expected maximum of N standard normals.
    expected_max_z = math.sqrt(2 * math.log(trials))
    return base_sharpe + expected_max_z * se


def evaluate(
    df: pd.DataFrame,
    ticker: str,
    strategy_id: str,
    params: dict[str, Any] | None = None,
    *,
    baseline_strategy: str = "buy_and_hold",
) -> Evaluation:
    """Evaluate one hypothesis in sample and out of sample.

    The in-sample numbers are what a searcher would have optimised toward. The
    out-of-sample numbers are the ones that count.
    """
    if strategy_id not in STRATEGY_META:
        raise HarnessError(f"unknown strategy: {strategy_id}")

    in_frame, out_frame = split_history(df)
    merged = {**(STRATEGY_META[strategy_id].default_params or {}), **(params or {})}

    def _run(frame: pd.DataFrame, sid: str, prm: dict[str, Any]) -> Any:
        try:
            return run_backtest(frame, ticker, sid, prm, fee_pct=FEE_PCT, rf_annual=RF_ANNUAL)
        except Exception as e:  # a broken hypothesis is a result, not a crash
            raise HarnessError(
                f"{sid} failed on {frame.index.min()}..{frame.index.max()}: {e}"
            ) from e

    ins = _window_result("in_sample", in_frame, _run(in_frame, strategy_id, merged))
    oos = _window_result("out_of_sample", out_frame, _run(out_frame, strategy_id, merged))
    base = _window_result(
        "baseline_out_of_sample",
        out_frame,
        _run(out_frame, baseline_strategy, STRATEGY_META[baseline_strategy].default_params or {}),
    )

    notes: list[str] = []
    edge = None
    if oos.sharpe_ratio is not None and base.sharpe_ratio is not None:
        edge = round(oos.sharpe_ratio - base.sharpe_ratio, 4)

    degradation = None
    if ins.sharpe_ratio is not None and oos.sharpe_ratio is not None:
        degradation = round(ins.sharpe_ratio - oos.sharpe_ratio, 4)

    # A large in-sample edge that vanishes out of sample is the signature of
    # fitting the past. Say so plainly rather than reporting the good half.
    overfit = bool(
        degradation is not None
        and ins.sharpe_ratio is not None
        and degradation > 0.5
        and ins.sharpe_ratio > 0
    )
    if overfit:
        notes.append(
            f"in-sample Sharpe {ins.sharpe_ratio:.2f} fell to {oos.sharpe_ratio:.2f} "
            "out of sample — likely fitted to the in-sample window"
        )
    is_always_in = strategy_id == "buy_and_hold"
    if not is_always_in and oos.trades is not None and oos.trades < 3:
        notes.append(f"only {oos.trades} out-of-sample trade(s); the result is close to noise")
    if not is_always_in and oos.time_in_market_pct is not None and oos.time_in_market_pct < 5:
        notes.append("barely in the market out of sample; the comparison is not meaningful")

    return Evaluation(
        ticker=ticker,
        strategy_id=strategy_id,
        params=merged,
        in_sample=ins.as_dict(),
        out_of_sample=oos.as_dict(),
        baseline_out_of_sample=base.as_dict(),
        edge_vs_baseline=edge,
        degradation=degradation,
        overfit_flag=overfit,
        notes=notes,
    )


def describe_harness() -> dict[str, Any]:
    """The fixed rules, so a result can be read years later without guessing."""
    return {
        "primary_metric": PRIMARY_METRIC,
        "metric_direction": "higher is better",
        "verdict_window": "out_of_sample",
        "out_of_sample_fraction": OUT_OF_SAMPLE_FRACTION,
        "min_observations": MIN_OBSERVATIONS,
        "fee_pct_per_side": FEE_PCT,
        "risk_free_annual": RF_ANNUAL,
        "baseline_strategy": "buy_and_hold",
        "strategies": sorted(STRATEGY_META),
        "note": (
            "The searcher sees in-sample results only. The out-of-sample window "
            "decides, and the bar rises with the number of experiments tried."
        ),
    }


__all__ = [
    "Evaluation",
    "HarnessError",
    "WindowResult",
    "describe_harness",
    "evaluate",
    "split_history",
    "trials_adjusted_hurdle",
]
