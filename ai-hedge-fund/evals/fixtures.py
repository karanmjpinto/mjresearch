"""Fixed inputs, so a golden case means the same thing next month.

A golden set run against live market data is not a golden set — the input moves
and a score change tells you nothing about the change you made. So the real
snapshots are captured once to `evals/fixtures/*.json` and the eval reads those.

`THIN` and `CONTRADICTORY` are constructed rather than captured, and they are
the only constructed inputs in the set. THIN is an almost-empty bundle;
CONTRADICTORY states a price and a valuation that cannot both be true. Both
exist to test what the app's own rules promise about missing and inconsistent
data, and neither pretends to be a real company — the ticker is `TEST`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DIR = Path(__file__).resolve().parent / "fixtures"

#: Real companies, captured from the live providers once. Chosen from this
#: app's own screen output — see `golden.py` for why each one is here.
CAPTURE = ("EXE", "TAP", "LULU", "KSS", "AAPL")

THIN: dict[str, Any] = {
    "ticker": "TEST",
    "note": "Deliberately sparse: the provider returned almost nothing.",
    "price": {"current": None},
    "fundamentals": {},
    "technicals": {},
}

CONTRADICTORY: dict[str, Any] = {
    "ticker": "TEST",
    "note": "Deliberately inconsistent. These figures cannot all be true at once.",
    "price": {"current": 10.0, "fifty_two_week_high": 8.0, "fifty_two_week_low": 12.0},
    "valuation": {"trailing_pe": -5.0, "price_to_book": 0.0, "market_cap": 0},
    "fundamentals": {"net_income_ttm": 500_000_000, "revenue_ttm": 1_000},
}

_SYNTHETIC = {"THIN": THIN, "CONTRADICTORY": CONTRADICTORY}


def load(name: str) -> dict[str, Any]:
    if name in _SYNTHETIC:
        return _SYNTHETIC[name]
    path = DIR / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"missing fixture {name}. Capture it first:\n"
            f"  uv run python scripts/run_eval.py --capture"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def available() -> list[str]:
    captured = sorted(p.stem for p in DIR.glob("*.json")) if DIR.is_dir() else []
    return captured + sorted(_SYNTHETIC)
