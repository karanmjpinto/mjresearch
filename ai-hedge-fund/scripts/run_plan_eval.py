"""Measure the plan pipeline the way Bridgewater measures PAT.

    uv run python scripts/run_plan_eval.py --capture          # once: freeze inputs
    uv run python scripts/run_plan_eval.py                    # 30 questions x 5 runs
    uv run python scripts/run_plan_eval.py --repeats 3 --limit 6   # a quick look
    uv run python scripts/run_plan_eval.py --coverage         # no model calls

PAT's headline figure is 95% output determinism on its test suite, and its
argument is that the figure comes first: a pipeline whose output moves between
runs cannot be evaluated, debugged or trusted, and no fix to it can be shown to
have worked. This script produces the four numbers that answer that for the
plan pipeline, on inputs that do not move:

  plan agreement        the same question gives the same plan (by plan hash)
  conclusion agreement  the same inputs give the same stance, conviction and
                        verification status — the figure comparable to PAT's
  grounded rate         runs whose prose checks clean against computed values
  coverage              share of the question set the metric catalog can
                        answer at all (see evals/plan_questions.py)

Inputs are frozen twice over: the snapshots in evals/fixtures/*.json, and
everything the plan fetches at execution time — price history, the macro
factors, peer sets and peer fundamentals — under evals/fixtures/{prices,macro,
peers}/, served instead of the live provider. A run on Monday and a run on Friday then see identical data, so any
difference between them belongs to the model or the code.

Not CI: it costs model time and its output is a measurement, not a pass/fail.
The parts that can be unit-tested — coverage and the agreement arithmetic —
are, in tests/test_plan_eval.py.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from evals import fixtures  # noqa: E402
from evals.plan_questions import QUESTIONS, coverage  # noqa: E402

PRICES = fixtures.DIR / "prices"
RESULTS = ROOT / "evals" / "results"

#: Long enough for every metric's default window, including the event study's
#: five years.
PRICE_DAYS = 1900

#: Named in the question set ("compare with Microsoft and Alphabet"), so their
#: fundamentals are frozen beside the fixtures' own peer sets.
NAMED_PEERS = ("MSFT", "GOOGL", "NKE")

MACRO = fixtures.DIR / "macro"
PEERS = fixtures.DIR / "peers"


def _cut(df: pd.DataFrame, end: str | None) -> pd.DataFrame:
    """Drop rows after the fixture's date, so every input describes one moment."""
    return df if not end else df[[str(i)[:10] <= str(end)[:10] for i in df.index]]


class FrozenPrices:
    """Serves the captured inputs in place of the live data service:
    price history, the macro factors, peer sets and peer fundamentals."""

    def __init__(self) -> None:
        self._frames: dict[str, pd.DataFrame] = {}
        self._peers = (
            json.loads((PEERS / "peers.json").read_text())
            if (PEERS / "peers.json").is_file()
            else {}
        )
        f = PEERS / "fundamentals.json"
        self._fundamentals = json.loads(f.read_text()) if f.is_file() else {}

    def _csv(self, path: Path) -> pd.DataFrame:
        key = str(path)
        if key not in self._frames:
            if not path.is_file():
                raise FileNotFoundError(f"{path.name} not frozen; run with --capture")
            self._frames[key] = pd.read_csv(path, index_col=0, parse_dates=True)
        return self._frames[key]

    def get_price_history(
        self, ticker: str, days: int = 365, end_date: Any = None, **_: Any
    ) -> pd.DataFrame:
        return self._csv(PRICES / f"{ticker.upper()}.csv").tail(int(days))

    def get_macro_data(self, series_id: str, days: int = 365 * 5) -> pd.DataFrame:
        df = self._csv(MACRO / f"{series_id}.csv")
        start = df.index.max() - pd.Timedelta(days=int(days))
        return df[df.index >= start]

    def get_peers(self, ticker: str) -> dict[str, Any]:
        return {"metrics": self._peers.get(ticker.upper(), {})}

    def get_fundamentals(self, ticker: str) -> dict[str, Any]:
        return self._fundamentals.get(ticker.upper(), {})


def capture() -> int:
    """Freeze every input the plan can fetch, cut at the fixtures' date."""
    from hedge_fund.data.service import get_data_service
    from hedge_fund.plan.market_metrics import FACTORS

    for d in (PRICES, MACRO, PEERS):
        d.mkdir(parents=True, exist_ok=True)
    ds = get_data_service()
    tickers = sorted({q.ticker for q in QUESTIONS})
    end = (fixtures.load(tickers[0]).get("price") or {}).get("window_end")
    for t in tickers:
        df = ds.get_price_history(t, days=PRICE_DAYS)
        if df is None or df.empty:
            print(f"  {t:6s} FAILED: no history")
            continue
        df = _cut(df, (fixtures.load(t).get("price") or {}).get("window_end"))
        df.to_csv(PRICES / f"{t}.csv")
        print(f"  {t:6s} {len(df)} price rows")
    for f in FACTORS.values():
        df = _cut(ds.get_macro_data(f.fred, days=PRICE_DAYS), end)
        df.to_csv(MACRO / f"{f.fred}.csv")
        print(f"  {f.fred:10s} {len(df)} rows")
    peers: dict[str, Any] = {}
    names: set[str] = set(NAMED_PEERS) | set(tickers)
    for t in tickers:
        found = ds.get_peers(t)
        peers[t] = dict(getattr(found, "metrics", None) or {})
        print(f"  {t:6s} peers {sorted(peers[t])}")
    (PEERS / "peers.json").write_text(json.dumps(peers, indent=1, default=str))
    funds = {n: ds.get_fundamentals(n) for n in sorted(names)}
    (PEERS / "fundamentals.json").write_text(json.dumps(funds, indent=1, default=str))
    print(f"  fundamentals for {sorted(funds)}")
    return 0


def agreement(values: list[Any]) -> float:
    """Share of runs that match the most common result. 1.0 is fully stable."""
    if not values:
        return 0.0
    return Counter(values).most_common(1)[0][1] / len(values)


async def run_once(q: Any, ds: FrozenPrices) -> dict[str, Any]:
    from hedge_fund.agents.plan_agent import run_plan_analysis

    t0 = time.perf_counter()
    out = await run_plan_analysis(
        q.ticker, fixtures.load(q.ticker), question=q.question, data_service=ds, persist=False
    )
    ms = int((time.perf_counter() - t0) * 1000)
    if "error" in out:
        return {"error": out["error"], "ms": ms}
    a, v, ex = out["analysis"], out["verification"], out["execution"]
    return {
        "plan_hash": ex["plan_hash"][:12],
        "metrics": [n["metric"] for n in ex["nodes"]],
        "conclusion": f"{a.get('stance')}|{a.get('conviction_score')}|{v['status']}",
        "grounded": v["status"] == "clean",
        "repaired": (out.get("repair") or {}).get("kept") == "repaired",
        "repair_tried": bool(out.get("repair")),
        # Clean before any repair: the rate the narrator manages alone.
        "first_draft_grounded": v["status"] == "clean" and not out.get("repair"),
        "clarifications": len(out["plan"]["clarifications"]),
        "cache_hits": ex["cache_hits"],
        "ms": ms,
    }


def score_question(q: Any, runs: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in runs if "error" not in r]
    return {
        "id": q.id,
        "ticker": q.ticker,
        "question": q.question,
        "runs": runs,
        "errors": len(runs) - len(ok),
        "plan_agreement": agreement([r["plan_hash"] for r in ok]),
        "conclusion_agreement": agreement([r["conclusion"] for r in ok]),
        "grounded_rate": sum(r["grounded"] for r in ok) / len(ok) if ok else 0.0,
    }


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for row in rows for r in row["runs"] if "error" not in r]
    n_runs = sum(len(row["runs"]) for row in rows)

    def mean(key: str) -> float:
        scored = [row[key] for row in rows if row["runs"] and row["errors"] < len(row["runs"])]
        return round(sum(scored) / len(scored), 3) if scored else 0.0

    return {
        "questions": len(rows),
        "runs": n_runs,
        "errored_runs": n_runs - len(ok),
        "plan_agreement": mean("plan_agreement"),
        "conclusion_agreement": mean("conclusion_agreement"),
        "grounded_rate": round(sum(r["grounded"] for r in ok) / len(ok), 3) if ok else 0.0,
        "first_draft_grounded_rate": (
            round(sum(r["first_draft_grounded"] for r in ok) / len(ok), 3) if ok else 0.0
        ),
        "repair_tried_rate": round(sum(r["repair_tried"] for r in ok) / len(ok), 3) if ok else 0.0,
        "repaired_rate": round(sum(r["repaired"] for r in ok) / len(ok), 3) if ok else 0.0,
        "asked_clarification_rate": (
            round(sum(r["clarifications"] > 0 for r in ok) / len(ok), 3) if ok else 0.0
        ),
        "median_ms": int(sorted(r["ms"] for r in ok)[len(ok) // 2]) if ok else None,
    }


async def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--capture", action="store_true", help="freeze every fetched input and exit")
    ap.add_argument("--coverage", action="store_true", help="report coverage only, no model calls")
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--limit", type=int, default=None, help="only the first N questions")
    ap.add_argument("--label", default="", help="a note stored with the result")
    ap.add_argument(
        "--unload-between-passes",
        action="store_true",
        help="stop the Ollama model before each pass, so no call can reuse a cached prompt",
    )
    args = ap.parse_args()

    if args.capture:
        return capture()

    cov = coverage()
    print(
        f"coverage: {cov['covered']}/{cov['total']} ({cov['share']:.0%})  blocked by {cov['blocked_by']}"
    )
    if args.coverage:
        return 0

    from hedge_fund.settings import settings

    qs = QUESTIONS[: args.limit] if args.limit else QUESTIONS
    ds = FrozenPrices()
    print(f"{len(qs)} questions x {args.repeats} runs, model={settings.ollama_model}\n")
    # Round robin, never the same question twice in a row. The model server
    # caches the previous prompt, and a repeat of it is computed differently
    # from a cold one: the first baseline ran each question five times in a
    # row and run 1 alone disagreed in 14 of the 15 split questions. A user
    # asks once, so the cold path is the one worth measuring.
    runs: dict[str, list[dict[str, Any]]] = {q.id: [] for q in qs}
    for rep in range(args.repeats):
        if args.unload_between_passes and settings.llm_provider == "ollama":
            # The server can match a prompt cached on an earlier pass from
            # another slot; unloading the model empties every slot.
            subprocess.run(["ollama", "stop", settings.ollama_model], check=False)
        for q in qs:
            runs[q.id].append(await run_once(q, ds))
        print(f"  pass {rep + 1}/{args.repeats} done")
    rows = [score_question(q, runs[q.id]) for q in qs]
    for row in rows:
        print(
            f"  {row['id']:22s} plan {row['plan_agreement']:.0%}  conclusion "
            f"{row['conclusion_agreement']:.0%}  grounded {row['grounded_rate']:.0%}"
            + (f"  errors {row['errors']}" if row["errors"] else "")
        )

    summary = summarise(rows)
    print("\n" + json.dumps(summary, indent=1))
    RESULTS.mkdir(parents=True, exist_ok=True)
    when = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS / f"plan-{when}.json"
    out.write_text(
        json.dumps(
            {
                "kind": "plan_eval",
                "when": when,
                "label": args.label,
                "model": settings.ollama_model,
                "repeats": args.repeats,
                "coverage": cov,
                "summary": summary,
                "questions": rows,
            },
            indent=1,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
