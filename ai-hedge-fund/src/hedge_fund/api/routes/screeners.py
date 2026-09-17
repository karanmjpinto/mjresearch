"""Screener endpoints — Yartseva Multibagger and future rules."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, NamedTuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hedge_fund.data.universes import list_universe_meta, load_universe
from hedge_fund.screeners import cache as screen_cache
from hedge_fund.screeners.acquisition_compounder import run_acquisition_compounder_for_ticker
from hedge_fund.screeners.yartseva import run_yartseva_for_ticker

router = APIRouter()
logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parents[4] / "config"


class ScreenerRunRequest(BaseModel):
    tickers: list[str] | None = Field(
        default=None,
        description="Symbols to screen. If set, overrides universe and watchlist_group.",
    )
    watchlist_group: str | None = Field(
        default="default",
        description="Watchlist key from config/watchlists.json when tickers and universe are empty.",
    )
    universe: str | None = Field(
        default=None,
        description="Index universe id: sp500, sp400, sp600 (see GET /screeners/universes).",
    )
    max_symbols: int = Field(
        default=500,
        ge=1,
        le=5000,
        description="Cap universe size after loading (large indices are slow per ticker).",
    )


# Backward-compatible alias
YartsevaRequest = ScreenerRunRequest


def _resolve_screener_tickers(
    req: ScreenerRunRequest,
) -> tuple[list[str], str | None, int | None, bool]:
    """Returns (tickers, universe_id, universe_total, truncated)."""
    universe_id: str | None = None
    universe_total: int | None = None
    truncated = False

    if req.tickers:
        return (
            [t.strip().upper() for t in req.tickers if t.strip()],
            None,
            None,
            False,
        )
    if req.universe and req.universe.strip():
        universe_id = req.universe.strip().lower()
        try:
            full = load_universe(universe_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.warning("universe load failed: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"failed to load universe {universe_id!r}: {e}",
            ) from e
        universe_total = len(full)
        tickers = full[: req.max_symbols]
        truncated = universe_total > len(tickers)
        return tickers, universe_id, universe_total, truncated

    tickers = _load_watchlist(req.watchlist_group or "default")
    return tickers, None, None, False


def _load_watchlist(group: str) -> list[str]:
    path = CONFIG_DIR / "watchlists.json"
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="watchlists.json not found",
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get(group)
    if not isinstance(raw, list) or not raw:
        raise HTTPException(
            status_code=400,
            detail=f"watchlist group {group!r} is missing or empty",
        )
    return [str(x).strip().upper() for x in raw if str(x).strip()]


@router.get("/universes")
async def get_universes():
    """Index / ETF proxy universes available for screeners."""
    return {"universes": list_universe_meta()}


@router.post("/yartseva")
async def run_yartseva(req: ScreenerRunRequest):
    """
    Run Yartseva Multibagger Stage 1 filters + Stage 2 composite scoring.

    Uses yfinance (quarterly TTM sums) — verify figures against filings before trading.
    """
    tickers, universe_id, universe_total, truncated = _resolve_screener_tickers(req)

    if not tickers:
        raise HTTPException(status_code=400, detail="no tickers to screen")

    results: list[dict] = []
    for t in tickers:
        results.append(await asyncio.to_thread(run_yartseva_for_ticker, t))

    def _sort_key(r: dict) -> tuple:
        c = r.get("composite")
        if c is None:
            return (1, 0.0)
        return (0, -float(c))

    results.sort(key=_sort_key)

    return {
        "macro_regime_note": (
            "Macro regime is portfolio-level: Fed stable/cutting = full weight; "
            "active hiking raise strong threshold to ~65+; aggressive hiking (>150bps) reduce exposure."
        ),
        "watchlist_group": req.watchlist_group if not req.tickers and not universe_id else None,
        "universe": universe_id,
        "universe_total": universe_total,
        "universe_truncated": truncated,
        "max_symbols": req.max_symbols if universe_id else None,
        "tickers": tickers,
        "count": len(results),
        "results": results,
    }


@router.post("/acquisition-compounder")
async def run_acquisition_compounder(req: ScreenerRunRequest):
    """
    Acquisition / bolt-on compounder: hard filters (growth, ROIC, FCF conversion, leverage,
    margins, dilution) + optional quality tier + 9-factor score (/45). Data is yfinance;
    organic growth uses revenue YoY / span CAGR proxies — verify in filings.
    """
    tickers, universe_id, universe_total, truncated = _resolve_screener_tickers(req)

    if not tickers:
        raise HTTPException(status_code=400, detail="no tickers to screen")

    results: list[dict] = []
    for t in tickers:
        results.append(await asyncio.to_thread(run_acquisition_compounder_for_ticker, t))

    def _sort_key(r: dict) -> tuple:
        ts = r.get("total_score")
        if ts is None:
            return (1, 0.0)
        return (0, -float(ts))

    results.sort(key=_sort_key)

    return {
        "methodology_note": (
            "Growth metrics use available annual FY columns or TTM series; when Yahoo returns "
            "short history, span-CAGR and revenueGrowth are approximations. Organic revenue "
            "uses YoY revenue growth as a proxy. Goodwill impairments may be incomplete. "
            "Not investment advice."
        ),
        "watchlist_group": req.watchlist_group if not req.tickers and not universe_id else None,
        "universe": universe_id,
        "universe_total": universe_total,
        "universe_truncated": truncated,
        "max_symbols": req.max_symbols if universe_id else None,
        "tickers": tickers,
        "count": len(results),
        "results": results,
    }


# ------------------------------------------------------------------
# Cached screens — a list to consult, not a job to commission
# ------------------------------------------------------------------

#: What each screen opens on, per screen rather than one shared default.
#:
#: They disagree about what a candidate even is. The multi-bagger screen has a
#: hard market-cap ceiling, so it cannot pass a single S&P 500 name — 502 of
#: 503 fail on size alone — and pointing it at the large-cap index leaves it
#: permanently, inexplicably empty. It gets the SmallCap 600, which is the band
#: it was written for. The compounder screen wants the scale serial acquirers
#: actually operate at, so it keeps the 500.
DEFAULT_UNIVERSE_FOR: dict[str, str] = {
    "yartseva": "sp600",
    "acquisition-compounder": "sp500",
    # All-cap by nature — Bolton ran a UK all-companies fund — but the 500 is
    # where "unloved" is most surprising and most liquid to act on.
    "bolton-contrarian": "sp500",
}

#: Fallback for anything not named above.
DEFAULT_UNIVERSE = "sp500"


class ScreenFields(NamedTuple):
    """Where each screen keeps its verdict, its score and its reasons.

    The screens were written at different times and do not agree on names —
    one has `stage1_passed` / `composite`, another `total_score`. This used to
    be an if-chain in the results route, which is how the compounder ended up
    sorted on a key that does not exist: the branch that handled it was the
    `else`, so nothing failed loudly, every row just scored zero and "ranked
    by score" quietly wasn't.

    A table means adding a screen is one row here rather than another branch
    nobody tests.
    """

    passed: str
    score: str
    failures: str


SCREEN_FIELDS: dict[str, ScreenFields] = {
    "yartseva": ScreenFields("stage1_passed", "composite", "stage1_failures"),
    "acquisition-compounder": ScreenFields("stage1_passed", "total_score", "stage1_failures"),
    "bolton-contrarian": ScreenFields("passed", "composite", "failures"),
}


def _default_universe(screen: str) -> str:
    return DEFAULT_UNIVERSE_FOR.get(screen, DEFAULT_UNIVERSE)


@router.get("/cached")
async def cached_screens() -> dict[str, Any]:
    """Which screens already have results, and how old they are."""
    return {
        "screens": screen_cache.available(),
        "default_universe": DEFAULT_UNIVERSE,
        "default_universe_for": DEFAULT_UNIVERSE_FOR,
        "refresh_command": "uv run python scripts/refresh_screens.py",
    }


@router.get("/{screen}/results")
async def screen_results(
    screen: str,
    universe: str | None = None,
    limit: int = 40,
    passing_only: bool = True,
) -> dict[str, Any]:
    """The last computed run of one screen, served without recomputing it.

    A screen is a list you consult, not a question you ask: at several seconds
    per name against yfinance, five hundred names is an hour, and nobody opens
    a screen they have to commission first. So this hands over the cache and
    says how old it is — the date is part of the answer, because a screen built
    on quarterly fundamentals is wrong the moment a company reports.
    """
    if screen not in screen_cache.SCREENS:
        raise HTTPException(404, f"unknown screen {screen!r}")

    # Resolved here rather than as a parameter default, because the default
    # depends on which screen was asked for.
    universe = (universe or "").strip().lower() or _default_universe(screen)

    got = screen_cache.read(screen, universe)
    if got is None:
        return {
            "screen": screen,
            "universe": universe,
            "available": False,
            "reason": (
                f"No {screen} results have been computed for {universe} yet. "
                "Run scripts/refresh_screens.py to build them."
            ),
            "refresh_command": (
                f"uv run python scripts/refresh_screens.py --universe {universe} --screen {screen}"
            ),
        }

    payload = got.as_dict()
    rows = payload.pop("results")

    # Errors are carried separately rather than filtered away: a name whose
    # data could not be fetched has not failed the screen, and folding the two
    # together turns "could not check" into "did not qualify".
    errored = [r for r in rows if r.get("error")]
    clean = [r for r in rows if not r.get("error")]

    fields = SCREEN_FIELDS.get(screen, SCREEN_FIELDS["acquisition-compounder"])
    passing = [r for r in clean if r.get(fields.passed)]
    ranked = sorted(
        passing if passing_only else clean,
        key=lambda r: (r.get(fields.score) is None, -(r.get(fields.score) or 0.0)),
    )
    score_key = fields.score

    # Why the ones that did not pass, did not. An empty screen showing only
    # "0 of 503 passed" is a dead end; the same screen saying "502 were above
    # the market-cap ceiling" tells you it is a small-cap screen pointed at the
    # wrong universe, which is the actual finding.
    failures: dict[str, int] = {}
    for r in clean:
        for f in r.get(fields.failures) or []:
            failures[str(f)] = failures.get(str(f), 0) + 1
    top_failures = [
        {"reason": k.replace("_", " "), "count": v}
        for k, v in sorted(failures.items(), key=lambda kv: -kv[1])[:5]
    ]

    return {
        **payload,
        "available": True,
        "top_failures": top_failures,
        "score_key": score_key,
        "checked": len(clean),
        "passing": len(passing),
        "shown": min(limit, len(ranked)),
        "errored": len(errored),
        "results": ranked[: max(1, limit)],
        "refresh_command": (
            f"uv run python scripts/refresh_screens.py --universe {universe} --screen {screen}"
        ),
    }
