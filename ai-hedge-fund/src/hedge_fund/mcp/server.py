"""MCP server exposing the AI hedge fund as tools.

Run directly:
    uv run hedge-fund-mcp

Or install as a Claude Desktop MCP server — see README for config snippet.

Tools exposed
-------------
- research_ticker        : Run AI committee analysis (parallel personas, rebuttal round on dissent, PM synthesis)
- get_market_data        : Price, fundamentals, technicals bundle for a ticker
- get_sec_filings        : Recent SEC filings (10-K, 10-Q, 8-K, Form 4, 13F, ...) via EDGAR
- get_peers              : SIC-classified peer group + side-by-side metrics
- run_backtest           : Rule-based strategy backtest (6 strategies, no look-ahead)
- optimize_portfolio     : Build weights via HRP / Markowitz / conviction-weighted / etc.
- describe_research_graph: Declarative view of the research workflow graph
- plan_research          : Typed-plan analysis — metrics computed by the harness, not the model
- list_metrics           : The deterministic metric catalog a plan may compose
- list_runs / get_run    : Recorded runs, for replay and comparison
- compare_runs           : Diff two runs; detects nondeterminism on identical inputs
- teach_methodology      : Store a portable method correction for future analyses
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from hedge_fund.agents.personas import (
    DEFAULT_COMMITTEE_PERSONAS,
    is_valid_persona,
    list_persona_ids,
)
from hedge_fund.agents import memory as _memory
from hedge_fund.agents.plan_agent import run_plan_analysis
from hedge_fund.agents.research_agent import (
    run_committee_analysis,
    run_research_analysis,
)
from hedge_fund.plan import catalog as _metric_catalog
from hedge_fund.runs import compare_runs as _compare_runs
from hedge_fund.runs import get_run as _get_run
from hedge_fund.runs import get_snapshot as _get_snapshot
from hedge_fund.runs import list_runs as _list_runs
from hedge_fund.api.research_snapshot import assemble_research_snapshot
from hedge_fund.data.service import get_data_service
from hedge_fund.orchestration import describe_research_graph as _describe_graph
from hedge_fund.quant.backtest import STRATEGY_META, run_backtest
from hedge_fund.quant.portfolio import METHOD_META, optimize_weights, portfolio_metrics

import numpy as np
import pandas as pd

logger = logging.getLogger("hedge_fund.mcp")

mcp = FastMCP("ai-hedge-fund")


# --- helpers ------------------------------------------------------------


def _ds():
    return get_data_service()


def _ok(payload: Any) -> str:
    """Serialize any tool result to a JSON string for MCP transport."""
    try:
        return json.dumps(payload, default=str, indent=2)
    except Exception as exc:
        return json.dumps({"error": "serialization_failed", "message": str(exc)})


def _normalize_price_df(raw: Any) -> pd.DataFrame | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        df = pd.DataFrame(raw)
    elif isinstance(raw, pd.DataFrame):
        df = raw.copy()
    else:
        return None
    if df.empty:
        return None
    df.columns = [str(c).lower() for c in df.columns]
    if "close" not in df.columns:
        for alt in ("adjclose", "adj close", "adjusted_close", "price"):
            if alt in df.columns:
                df = df.rename(columns={alt: "close"})
                break
    if "close" not in df.columns:
        return None
    if "date" in df.columns:
        df = df.set_index(pd.to_datetime(df["date"])).drop(columns=["date"])
    elif not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna(subset=["close"])


# --- tools --------------------------------------------------------------


@mcp.tool()
async def research_ticker(
    ticker: str,
    mode: str = "committee",
    persona: str | None = None,
) -> str:
    """Run AI research on a ticker.

    mode="committee" (default) runs a parallel committee of 4 named investors
    (Warren Buffett, Ben Graham, Cathie Wood, Michael Burry) and a Portfolio
    Manager synthesis node. If the committee splits materially, each analyst is
    first shown the others' anonymized conclusions against the same snapshot and
    either revises or holds; the `refinement` block records what moved.
    mode="persona" runs a single named investor (set `persona` to one of the ids
    returned by describe_research_graph). mode="default" runs a generic analyst.
    """
    ticker = ticker.upper().strip()
    flat, llm_snapshot = await assemble_research_snapshot(ticker, _ds(), price_days=30)

    if mode == "committee":
        result = await run_committee_analysis(
            ticker, llm_snapshot, list(DEFAULT_COMMITTEE_PERSONAS)
        )
    elif mode == "persona":
        if not persona or not is_valid_persona(persona):
            return _ok(
                {
                    "error": "invalid_persona",
                    "message": f"Unknown persona {persona!r}",
                    "available": list_persona_ids(),
                }
            )
        result = await run_research_analysis(ticker, llm_snapshot, persona_id=persona)
    else:
        result = await run_research_analysis(ticker, llm_snapshot, persona_id="default")

    return _ok(
        {
            "ticker": ticker,
            "mode": mode,
            "persona": persona,
            "result": result,
            "snapshot_summary": {
                "price_current": flat.get("price", {}).get("current"),
                "sector": (flat.get("fundamentals") or {}).get("sector"),
                "news_count": len(flat.get("news", []) or []),
            },
        }
    )


@mcp.tool()
async def get_market_data(ticker: str, days: int = 180) -> str:
    """Return a full market-data snapshot: price series, fundamentals, technicals, news.

    `days` controls the price window length (default 180).
    """
    ticker = ticker.upper().strip()
    flat, _ = await assemble_research_snapshot(ticker, _ds(), price_days=max(30, min(days, 3650)))
    return _ok(flat)


@mcp.tool()
async def get_sec_filings(ticker: str) -> str:
    """Recent SEC filings for a ticker via EDGAR.

    Returns form type, filed date, description, and report URL for 10-K, 10-Q,
    8-K, Form 4 (insider), 13F-HR (institutional), DEF 14A, SC 13G/D.
    """
    ticker = ticker.upper().strip()
    result = _ds().get_filings(ticker)
    if result is None:
        return _ok({"ticker": ticker, "filings": [], "error": "no_data"})
    filings = [f.model_dump() if hasattr(f, "model_dump") else f for f in result]
    return _ok({"ticker": ticker, "count": len(filings), "filings": filings})


@mcp.tool()
async def get_peers(ticker: str) -> str:
    """SIC-classified peer group via EDGAR + yfinance metrics (P/E, margin, ROE, etc.).

    Returns the target ticker's sector/industry and up to 10 peer tickers ranked
    by market cap, with per-asset fundamentals for side-by-side comparison.
    """
    ticker = ticker.upper().strip()
    result = _ds().get_peers(ticker)
    if result is None:
        return _ok({"ticker": ticker, "error": "no_data"})
    return _ok(result.model_dump() if hasattr(result, "model_dump") else result)


@mcp.tool()
async def run_backtest_tool(
    ticker: str,
    strategy: str = "golden_cross",
    days: int = 1095,
    fee_bps: int = 5,
) -> str:
    """Run a rule-based backtest on a ticker.

    Available strategies: buy_and_hold, golden_cross, rsi_reversion,
    bollinger_breakout, trend_and_drawdown, momentum.

    `days` = lookback window (default 3 years). `fee_bps` = one-way transaction
    cost in basis points (default 5 = 0.05%). Signals use a one-bar lag
    (no look-ahead).
    """
    ticker = ticker.upper().strip()
    if strategy not in STRATEGY_META:
        return _ok(
            {
                "error": "unknown_strategy",
                "available": list(STRATEGY_META.keys()),
            }
        )
    raw = _ds().get_price_history(ticker, days=max(60, min(days, 3650)))
    df = _normalize_price_df(raw)
    if df is None or df.empty:
        return _ok({"ticker": ticker, "error": "no_price_data"})
    try:
        result = run_backtest(
            df=df,
            ticker=ticker,
            strategy_id=strategy,
            fee_pct=fee_bps / 10000.0,
        )
    except ValueError as exc:
        return _ok({"ticker": ticker, "error": str(exc)})
    out = result.to_dict()
    # Trim equity curve to keep MCP transport fast
    out["equity_curve"] = out["equity_curve"][:: max(1, len(out["equity_curve"]) // 200)]
    return _ok(out)


@mcp.tool()
async def optimize_portfolio(
    tickers: list[str],
    method: str = "hrp",
    days: int = 730,
    convictions: dict[str, float] | None = None,
) -> str:
    """Build portfolio weights for a basket.

    Methods:
      - equal_weight: 1/N baseline
      - conviction_weighted: weight ∝ AI conviction, <40 filtered out
      - inverse_vol: weight ∝ 1/σ
      - mean_variance: Markowitz max-Sharpe (blends conviction if supplied)
      - hrp: Hierarchical Risk Parity (Lopez de Prado 2016) — default

    `convictions` is an optional {ticker: 0-100} map; used by
    conviction_weighted and mean_variance.
    """
    if method not in METHOD_META:
        return _ok({"error": "unknown_method", "available": list(METHOD_META.keys())})

    clean = [t.upper().strip() for t in tickers if t and t.strip()]
    clean = list(dict.fromkeys(clean))
    if len(clean) < 2:
        return _ok({"error": "need_at_least_2_tickers", "received": clean})

    closes: dict[str, pd.Series] = {}
    for t in clean:
        raw = _ds().get_price_history(t, days=max(60, min(days, 3650)))
        df = _normalize_price_df(raw)
        if df is None or "close" not in df.columns or len(df) < 20:
            continue
        closes[t] = df["close"]

    if len(closes) < 2:
        return _ok(
            {
                "error": "insufficient_price_data",
                "requested": clean,
                "available": list(closes.keys()),
            }
        )

    prices = pd.concat(closes, axis=1).dropna(how="any")
    if len(prices) < 20:
        return _ok({"error": "too_few_common_bars", "bars": int(len(prices))})

    returns = prices.pct_change().dropna()
    w = optimize_weights(method, returns, convictions)
    metrics = portfolio_metrics(w, returns)
    eq_metrics = portfolio_metrics(
        np.full(len(returns.columns), 1.0 / len(returns.columns)), returns
    )

    assets = []
    for i, t in enumerate(returns.columns):
        asset_ret = float(returns[t].mean() * 252)
        asset_vol = float(returns[t].std() * np.sqrt(252))
        assets.append(
            {
                "ticker": t,
                "weight": round(float(w[i]), 6),
                "expected_return": round(asset_ret, 6),
                "volatility": round(asset_vol, 6),
                "conviction": (float(convictions[t]) if convictions and t in convictions else None),
            }
        )

    # Strip heavy equity curves from the metrics before emitting
    for m in (metrics, eq_metrics):
        m.pop("equity_curve", None)

    return _ok(
        {
            "method_id": method,
            "method_name": METHOD_META[method].name,
            "start_date": str(prices.index[0].date()),
            "end_date": str(prices.index[-1].date()),
            "n_bars": int(len(returns)),
            "assets": assets,
            "metrics": metrics,
            "equal_weight_metrics": eq_metrics,
            "excluded_tickers": [t for t in clean if t not in closes],
        }
    )


@mcp.tool()
async def describe_research_graph(persona_ids: list[str] | None = None) -> str:
    """Return the structure of the AI research workflow (nodes + edges).

    Useful for understanding how a ticker gets researched: market data is
    fanned out to N parallel persona nodes, each emits a JSON analysis, and
    the Portfolio Manager reduce node synthesizes a final thesis.
    """
    return _ok(_describe_graph(persona_ids))


@mcp.tool()
async def plan_research(
    ticker: str,
    question: str = "",
    style: str | None = None,
    replay_snapshot: str | None = None,
) -> str:
    """Research a ticker by compiling the question into a typed plan.

    Unlike `research_ticker`, the model never produces a number here. It selects
    deterministic metrics from a fixed catalog (see `list_metrics`), the harness
    computes them, and a second pass writes the thesis over those computed values
    only. If the plan computes a conviction score it overrides whatever the model
    wrote — the substitution is reported under `harness_overrides`.

    Args:
        ticker: Symbol to analyse.
        question: What to answer. Defaults to whether the name is attractive now.
        style: Investing style to reflect in metric choice and weights.
        replay_snapshot: Snapshot hash to reuse instead of fetching fresh data,
            which reproduces a past run exactly.
    """
    sym = ticker.strip().upper()
    if replay_snapshot:
        snapshot = _get_snapshot(replay_snapshot)
        if snapshot is None:
            return _ok({"error": "snapshot_not_found", "snapshot_sha256": replay_snapshot})
    else:
        _base, snapshot = await assemble_research_snapshot(sym, _ds(), price_days=30)

    result = await run_plan_analysis(
        sym, snapshot, question=question, style=style, data_service=_ds()
    )
    return _ok(result)


@mcp.tool()
async def list_metrics() -> str:
    """List every deterministic metric a plan may use, with its typed signature.

    Each entry declares its parameters and every field it emits, with a semantic
    description — this is the full set of figures an analysis can be built from.
    """
    specs = _metric_catalog()
    return _ok({"count": len(specs), "metrics": specs})


@mcp.tool()
async def list_runs(ticker: str | None = None, mode: str | None = None, limit: int = 25) -> str:
    """List recorded research runs, newest first.

    Args:
        ticker: Restrict to one symbol.
        mode: One of single, persona, committee, plan.
        limit: Maximum rows to return.
    """
    runs = _list_runs(ticker=ticker, mode=mode, limit=limit)
    return _ok({"count": len(runs), "runs": runs})


@mcp.tool()
async def get_run(run_uid: str, include_snapshot: bool = False) -> str:
    """Fetch one recorded run, optionally with the exact data it analysed."""
    run = _get_run(run_uid, include_snapshot=include_snapshot)
    if run is None:
        return _ok({"error": "run_not_found", "run_uid": run_uid})
    return _ok(run)


@mcp.tool()
async def compare_runs(run_uid_a: str, run_uid_b: str) -> str:
    """Diff two runs.

    `nondeterminism_detected` is the field worth watching: it means two runs with
    identical inputs reached different conclusions, so results are not yet
    reproducible and any evaluation built on them would be measuring noise.
    """
    return _ok(_compare_runs(run_uid_a, run_uid_b))


@mcp.tool()
async def teach_methodology(
    note: str,
    scope_ticker: str | None = None,
    scope_persona: str | None = None,
    tags: list[str] | None = None,
    source_run_uid: str | None = None,
) -> str:
    """Teach the system a better *method*, which later analyses will apply.

    Write what should be done differently next time — an approach, not an answer.
    Notes containing prices, amounts, or scores are rejected: a stored number
    would be replayed onto every future run, where it will not be true.

    Args:
        note: The methodology lesson, in plain language.
        scope_ticker: Limit to one symbol. Omit if the lesson generalises.
        scope_persona: Limit to one investor persona.
        tags: Optional labels for organisation.
        source_run_uid: The run that prompted the lesson.
    """
    try:
        saved = _memory.add_note(
            note,
            tags=tags,
            scope_ticker=scope_ticker,
            scope_persona=scope_persona,
            source_run_uid=source_run_uid,
        )
    except _memory.MethodologyError as e:
        return _ok({"error": "rejected", "message": str(e)})
    return _ok({"ok": True, "note": saved})


# --- entrypoint ---------------------------------------------------------


def main() -> None:
    """Run the MCP server over stdio (the mode Claude Desktop uses)."""
    # Make sure asyncio has a usable policy on platforms that need it
    try:
        asyncio.get_event_loop_policy()
    except Exception:
        pass
    mcp.run()


if __name__ == "__main__":
    main()
