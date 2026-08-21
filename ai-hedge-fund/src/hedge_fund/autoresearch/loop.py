"""The overnight loop: propose, evaluate, keep or discard, log, repeat.

The searcher proposes a strategy and parameters from a fixed registry rather
than editing code. That is a deliberate narrowing of karpathy's setup, where the
agent rewrites the training script: an unbounded search over generated code is
reasonable when the worst case is a wasted GPU hour, and unreasonable when the
output is a trading rule. A bounded space also keeps every experiment
comparable, which is the property the whole exercise depends on.

The searcher is shown in-sample results and never the out-of-sample window, for
the same reason a student does not get the exam paper in advance.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from hedge_fund.agents.llm import call_json
from hedge_fund.autoresearch import store
from hedge_fund.autoresearch.harness import (
    HarnessError,
    describe_harness,
    evaluate,
    trials_adjusted_hurdle,
)
from hedge_fund.quant.backtest import STRATEGY_META

logger = logging.getLogger(__name__)

BASELINE_STRATEGY = "buy_and_hold"
# Attempts allowed before giving up on getting a non-duplicate proposal.
MAX_PROPOSAL_ATTEMPTS = 3


class Hypothesis(BaseModel):
    """One proposal. Deliberately small — the space is the registry, not code."""

    ticker: str = Field(max_length=32)
    strategy_id: str = Field(max_length=64)
    params: dict[str, float] = Field(default_factory=dict)
    hypothesis: str = Field(default="", max_length=400)
    reasoning: str = Field(default="", max_length=800)


def _config_key(ticker: str, strategy_id: str, params: dict[str, Any]) -> str:
    """Identity of a configuration, for detecting an exact repeat."""
    return json.dumps(
        {
            "t": ticker.upper(),
            "s": strategy_id,
            "p": {
                k: round(float(v), 6)
                for k, v in sorted((params or {}).items())
                if isinstance(v, (int, float))
            },
        },
        sort_keys=True,
    )


def _tried_keys(history: list[dict[str, Any]]) -> set[str]:
    return {
        _config_key(r["ticker"], r["strategy_id"], r.get("params") or {})
        for r in history
        if r.get("strategy_id")
    }


def _coverage_gaps(history: list[dict[str, Any]], tickers: list[str]) -> list[str]:
    """Ticker/strategy-family combinations not yet attempted.

    Observed failure mode: left to itself the proposer nudges one parameter on
    one name for the whole run. Naming the untouched ground explicitly is more
    effective than asking it to be creative.
    """
    seen = {(r["ticker"], r["strategy_id"]) for r in history if not r.get("is_baseline")}
    gaps = [
        f"{t} + {sid}"
        for t in tickers
        for sid in sorted(STRATEGY_META)
        if sid != BASELINE_STRATEGY and (t, sid) not in seen
    ]
    return gaps


PROPOSER_SYSTEM = """You are the proposing stage of an automated research loop.

You choose ONE experiment at a time: a ticker, a strategy from the catalog, and
its parameters. You do not evaluate it — a fixed harness does that, and you
never see the out-of-sample window it judges on.

Rules:
- Use only strategy ids and parameter names from the catalog. Never invent one.
- Read the log of previous experiments. Do not repeat a configuration already
  tried; vary something specific and say what you changed and why.
- Prefer a small number of meaningful moves over many tiny parameter nudges.
  Every experiment raises the bar the eventual winner must clear.
- A discarded result is information. If a family of strategies keeps failing on
  a name, move to a different family rather than tuning it further.
- Output valid JSON only.
"""


def _catalog() -> str:
    lines = []
    for sid, meta in sorted(STRATEGY_META.items()):
        lines.append(f"- {sid} ({meta.category}): {meta.description}")
        if meta.default_params:
            lines.append(f"    params: {json.dumps(meta.default_params)}")
    return "\n".join(lines)


def _history_digest(rows: list[dict[str, Any]], limit: int = 24) -> str:
    """Prior experiments as the searcher sees them: in-sample only."""
    if not rows:
        return "(no experiments yet)"
    out = []
    for r in rows[:limit]:
        ins = (r.get("in_sample") or {}).get("sharpe_ratio")
        out.append(
            f"#{r['seq']} {r['ticker']} {r['strategy_id']} {json.dumps(r.get('params') or {})} "
            f"-> in-sample sharpe {ins if ins is not None else 'n/a'} [{r['verdict']}]"
        )
    return "\n".join(out)


async def propose(
    run_tag: str, tickers: list[str], history: list[dict[str, Any]], *, retry: int = 0
) -> tuple[Hypothesis | None, dict[str, Any]]:
    """Ask for the next experiment, constrained to the registry."""
    nudge = (
        "\n\nYour previous proposal repeated a configuration already tried. "
        "Choose a DIFFERENT ticker or a different strategy family."
        if retry
        else ""
    )
    gaps = _coverage_gaps(history, tickers)
    gap_line = (
        "Not yet attempted at all (prefer these before tuning something already tried):\n"
        + "\n".join(f"  - {g}" for g in gaps[:20])
        if gaps
        else "Every ticker/strategy pair has been attempted at least once; vary parameters meaningfully."
    )
    user = f"""Universe: {", ".join(tickers)}

Strategy catalog:
{_catalog()}

Previous experiments (in-sample only — the out-of-sample window is withheld):
{_history_digest(history)}

{gap_line}

Propose the next single experiment as JSON:
{{"ticker": "...", "strategy_id": "...", "params": {{}}, "hypothesis": "one line", "reasoning": "why this next"}}
"""
    try:
        result = await call_json(PROPOSER_SYSTEM + nudge, user, Hypothesis.model_json_schema())
    except Exception as e:
        logger.exception("Proposer failed for run %s", run_tag)
        return None, {"error": str(e)}

    try:
        h = Hypothesis.model_validate_json(result.content)
    except Exception as e:
        return None, {"error": f"unparseable proposal: {e}", "raw": result.content[:300]}

    h.ticker = h.ticker.strip().upper()
    if h.strategy_id not in STRATEGY_META:
        return None, {"error": f"unknown strategy: {h.strategy_id}"}
    if h.ticker not in {t.upper() for t in tickers}:
        return None, {"error": f"{h.ticker} is outside the universe"}
    return h, {"model": result.model}


def _record(
    run_tag: str,
    seq: int,
    *,
    ticker: str,
    strategy_id: str,
    params: dict[str, Any],
    ev: Any = None,
    hurdle: float | None = None,
    kept: bool = False,
    verdict: str = "discarded",
    is_baseline: bool = False,
    hypothesis: str | None = None,
    reasoning: str | None = None,
    error: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    oos = (ev.out_of_sample if ev else None) or {}
    row = {
        "run_tag": run_tag,
        "seq": seq,
        "ticker": ticker,
        "strategy_id": strategy_id,
        "params": params,
        "hypothesis": hypothesis,
        "is_baseline": is_baseline,
        "kept": kept,
        "verdict": verdict,
        "in_sample": (ev.in_sample if ev else None),
        "out_of_sample": oos or None,
        "baseline_out_of_sample": (ev.baseline_out_of_sample if ev else None),
        "primary_metric": oos.get("sharpe_ratio"),
        "edge_vs_baseline": (ev.edge_vs_baseline if ev else None),
        "degradation": (ev.degradation if ev else None),
        "hurdle": hurdle,
        "overfit_flag": bool(ev.overfit_flag) if ev else False,
        "notes": (ev.notes if ev else None),
        "reasoning": reasoning,
        "error": error,
        "model": model,
    }
    store.record(**row)
    return row


def run_baseline(run_tag: str, ticker: str, data_service: Any, days: int) -> dict[str, Any]:
    """Establish the number to beat before anything is proposed."""
    seq = store.next_seq(run_tag)
    df = data_service.get_price_history(ticker, days=days)
    try:
        ev = evaluate(df, ticker, BASELINE_STRATEGY)
    except HarnessError as e:
        return _record(
            run_tag,
            seq,
            ticker=ticker,
            strategy_id=BASELINE_STRATEGY,
            params={},
            verdict="error",
            error=str(e),
            is_baseline=True,
        )
    return _record(
        run_tag,
        seq,
        ticker=ticker,
        strategy_id=BASELINE_STRATEGY,
        params=ev.params,
        ev=ev,
        kept=True,
        verdict="baseline",
        is_baseline=True,
        hypothesis="Baseline: hold the asset.",
    )


async def run_loop(
    run_tag: str,
    tickers: list[str],
    *,
    data_service: Any,
    experiments: int = 10,
    days: int = 1825,
    max_seconds: float | None = None,
) -> dict[str, Any]:
    """Run the loop. Returns a summary; every experiment is persisted as it goes.

    Nothing here is a recommendation. A surviving result is a hypothesis that
    has not yet been eliminated on data it was not fitted to.
    """
    started = time.perf_counter()
    tickers = [t.strip().upper() for t in tickers if t.strip()]
    if not tickers:
        return {"error": "no tickers supplied"}

    baselines = {t: run_baseline(run_tag, t, data_service, days) for t in tickers}

    for _ in range(max(1, experiments)):
        if max_seconds is not None and (time.perf_counter() - started) > max_seconds:
            break

        history = store.list_experiments(run_tag, limit=60)
        tried = _tried_keys(history)

        # An exact repeat tells us nothing and would raise the significance bar
        # for everything after it, so it is refused rather than recorded.
        hypothesis = None
        meta: dict[str, Any] = {}
        for attempt in range(MAX_PROPOSAL_ATTEMPTS):
            candidate, meta = await propose(run_tag, tickers, history, retry=attempt)
            if candidate is None:
                break
            if _config_key(candidate.ticker, candidate.strategy_id, candidate.params) in tried:
                logger.info(
                    "Duplicate proposal rejected: %s %s", candidate.ticker, candidate.strategy_id
                )
                meta = {**meta, "error": "proposer repeated a configuration already tried"}
                continue
            hypothesis = candidate
            break

        seq = store.next_seq(run_tag)

        if hypothesis is None:
            _record(
                run_tag,
                seq,
                ticker=tickers[0],
                strategy_id="?",
                params={},
                verdict="error",
                error=str(meta.get("error"))[:400],
            )
            continue

        df = data_service.get_price_history(hypothesis.ticker, days=days)
        try:
            ev = evaluate(df, hypothesis.ticker, hypothesis.strategy_id, hypothesis.params)
        except HarnessError as e:
            _record(
                run_tag,
                seq,
                ticker=hypothesis.ticker,
                strategy_id=hypothesis.strategy_id,
                params=hypothesis.params,
                verdict="error",
                error=str(e),
                hypothesis=hypothesis.hypothesis,
                reasoning=hypothesis.reasoning,
                model=meta.get("model"),
            )
            continue

        base = baselines.get(hypothesis.ticker) or {}
        base_sharpe = ((base.get("out_of_sample") or {}).get("sharpe_ratio")) or 0.0
        obs = (ev.out_of_sample or {}).get("observations") or 0
        hurdle = trials_adjusted_hurdle(store.trial_count(run_tag) + 1, obs, base_sharpe)

        oos_sharpe = (ev.out_of_sample or {}).get("sharpe_ratio")
        # Keep only what clears the trials-adjusted bar out of sample, and only
        # if it did not obviously fit the in-sample window.
        kept = bool(oos_sharpe is not None and oos_sharpe > hurdle and not ev.overfit_flag)

        _record(
            run_tag,
            seq,
            ticker=hypothesis.ticker,
            strategy_id=hypothesis.strategy_id,
            params=hypothesis.params,
            ev=ev,
            hurdle=round(hurdle, 4),
            kept=kept,
            verdict="kept" if kept else "discarded",
            hypothesis=hypothesis.hypothesis,
            reasoning=hypothesis.reasoning,
            model=meta.get("model"),
        )

    summary = store.summarize(run_tag)
    summary["elapsed_seconds"] = round(time.perf_counter() - started, 1)
    summary["harness"] = describe_harness()
    summary["baselines"] = {
        t: (b.get("out_of_sample") or {}).get("sharpe_ratio") for t, b in baselines.items()
    }
    return summary
