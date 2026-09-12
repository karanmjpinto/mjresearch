"""Curated comparable companies.

Peers arrive from EDGAR's SIC classification, which is a 1970s taxonomy. Apple's
SIC 3571 ("Electronic Computers") contains Socket Mobile and One Stop Systems,
and does not contain Microsoft or Alphabet. Ranking that bucket by market cap
does not rescue it: the bucket is wrong, not badly sorted, and a football field
drawn from it is wrong before it is drawn.

So a comparison set is a judgment, and this module makes it one. `config/comps.json`
holds hand-picked peers with a stated reason per name, in the same spirit as
`config/watchlists.json`. Two rules follow from treating it as judgment:

* A curated set **replaces** the automatic one rather than being blended into it.
  A vetted set diluted with SIC noise is no longer vetted.
* Where no curated set exists the automatic list still shows, flagged `vetted:
  False` with `basis: "sic"`, so the screen can say the set is unreviewed instead
  of implying someone chose it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hedge_fund.data.models import PeerComparison

logger = logging.getLogger(__name__)

DEFAULT_COMPS_PATH = Path(__file__).resolve().parents[3] / "config" / "comps.json"

#: Kept identical to the keys the EDGAR provider emits, so a curated set and a
#: fallback set populate the same columns and the radar does not change shape
#: depending on which path produced the row.
METRIC_KEYS = (
    "pe_ratio",
    "forward_pe",
    "price_to_book",
    "profit_margin",
    "return_on_equity",
    "revenue_growth",
    "dividend_yield",
    "beta",
    "market_cap",
)


@dataclass(frozen=True)
class CuratedSet:
    """A hand-picked comparison set for one ticker."""

    ticker: str
    peers: tuple[str, ...]
    reasons: Mapping[str, str]
    as_of: str | None = None


def _norm(ticker: str) -> str:
    return ticker.strip().upper()


def load_curated(path: Path | None = None) -> dict[str, CuratedSet]:
    """Read the curated sets. A missing or malformed file is not an error.

    Comps are an input you edit by hand, so the app has to keep working when the
    file is absent, half-written, or being edited — it falls back to the
    automatic set and says so, rather than failing the request.
    """
    p = path or DEFAULT_COMPS_PATH
    try:
        raw = json.loads(p.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("comps.json unreadable (%s); falling back to automatic peers", exc)
        return {}

    entries = raw.get("comps") if isinstance(raw, dict) else None
    if not isinstance(entries, dict):
        return {}

    out: dict[str, CuratedSet] = {}
    for ticker, spec in entries.items():
        if not isinstance(spec, dict):
            continue
        peers: list[str] = []
        reasons: dict[str, str] = {}
        seen: set[str] = set()
        self_t = _norm(ticker)
        for item in spec.get("peers") or []:
            if isinstance(item, str):
                t, reason = _norm(item), ""
            elif isinstance(item, dict) and item.get("ticker"):
                t, reason = _norm(str(item["ticker"])), str(item.get("reason") or "")
            else:
                continue
            # A ticker is not its own comparable, and a duplicate would be
            # counted twice in every average drawn from the set.
            if not t or t == self_t or t in seen:
                continue
            seen.add(t)
            peers.append(t)
            if reason:
                reasons[t] = reason
        if peers:
            out[self_t] = CuratedSet(
                ticker=self_t,
                peers=tuple(peers),
                reasons=reasons,
                as_of=str(spec["as_of"]) if spec.get("as_of") else None,
            )
    return out


def _metrics_for(tickers: list[str], fundamentals: Callable[[str], dict]) -> dict[str, dict]:
    """Compact fundamentals per ticker, best-effort.

    One bad symbol must not empty the whole table, so a failure is recorded as
    absent metrics for that name and the rest of the set still renders.
    """
    out: dict[str, dict[str, Any]] = {}
    for t in tickers:
        try:
            data = fundamentals(t) or {}
        except Exception as exc:  # a provider outage is not a reason to 500
            logger.debug("comps metrics for %s failed: %s", t, exc)
            continue
        if data.get("error"):
            continue
        row = {k: data.get(k) for k in METRIC_KEYS if data.get(k) is not None}
        if row:
            out[t] = row
    return out


def apply_curated(
    ticker: str,
    auto: PeerComparison | None,
    curated: Mapping[str, CuratedSet] | None = None,
    fundamentals: Callable[[str], dict] | None = None,
) -> PeerComparison | None:
    """Overlay the curated set for `ticker`, or label the automatic one unvetted."""
    t = _norm(ticker)
    sets = curated if curated is not None else load_curated()
    pick = sets.get(t)

    if pick is None:
        if auto is None:
            return None
        auto.basis = "sic" if auto.peers else "none"
        auto.vetted = False
        return auto

    metrics: dict[str, dict] = {}
    if fundamentals is not None:
        metrics = _metrics_for([t, *pick.peers], fundamentals)

    sector = auto.sector if auto else None
    industry = auto.industry if auto else None
    if fundamentals is not None and (sector is None or industry is None):
        try:
            own = fundamentals(t) or {}
            sector = sector or own.get("sector")
            industry = industry or own.get("industry")
        except Exception:  # noqa: BLE001 — sector is a label, not worth failing over
            pass

    return PeerComparison(
        ticker=t,
        peers=list(pick.peers),
        sector=sector,
        industry=industry,
        metrics=metrics,
        source="curated" if auto is None else f"curated+{auto.source}",
        basis="curated",
        vetted=True,
        peer_reasons=dict(pick.reasons),
        as_of=pick.as_of,
    )
