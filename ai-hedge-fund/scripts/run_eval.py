"""Run the golden set against the live model and score it.

    uv run python scripts/run_eval.py --capture     # once: freeze the inputs
    uv run python scripts/run_eval.py               # score all 20 cases
    uv run python scripts/run_eval.py --case lens-bolton-rejects-expensive
    uv run python scripts/run_eval.py --model qwen3.5:35b   # compare a model

Why this exists: the app has several hundred tests over its deterministic code
and, until now, none over the part that is predicted rather than calculated.
That gap made three separate questions unanswerable in one afternoon — which
temperature, which prompt ordering, and whether a persona was right — because
every one of them needs a bar to measure against.

Two disciplines borrowed from the Studio framework's eval-first-spec:

  - **Establish the naked baseline first.** Record what the current
    configuration scores before changing anything, or you never learn what a
    change was worth. Results are written to `evals/results/` for exactly that.
  - **Cost per outcome, to the cent.** Printed at the end. A run is cheap here
    because the model is local, but the token count is the honest number and it
    is what a hosted model would bill for.

This is not CI. It costs minutes of GPU time and its output moves; the graders
themselves are unit-tested in `tests/test_eval_harness.py`, which is what runs
on every commit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from evals import fixtures  # noqa: E402
from evals.golden import CASES, Case  # noqa: E402
from hedge_fund.agents.research_agent import run_research_analysis  # noqa: E402
from hedge_fund.settings import settings  # noqa: E402

RESULTS = ROOT / "evals" / "results"


async def capture() -> int:
    """Freeze the real snapshots once, so the inputs stop moving."""
    from hedge_fund.api.research_snapshot import assemble_research_snapshot
    from hedge_fund.data.service import get_data_service

    fixtures.DIR.mkdir(parents=True, exist_ok=True)
    ds = get_data_service()
    for ticker in fixtures.CAPTURE:
        try:
            _, snap = await assemble_research_snapshot(ticker, ds, price_days=30, end_date=None)
        except Exception as exc:  # noqa: BLE001
            print(f"  {ticker:6s} FAILED: {str(exc)[:80]}")
            continue
        path = fixtures.DIR / f"{ticker}.json"
        path.write_text(json.dumps(snap, indent=1, default=str), encoding="utf-8")
        print(f"  {ticker:6s} captured  {path.stat().st_size / 1000:.0f} kB")
    return 0


#: No single verdict may account for more than this share of the set.
#:
#: This is the check the per-case graders cannot make, and it exists because
#: the set without it endorsed the wrong change. Scoring `llm_shared_prefix`
#: on the shipped path: the reorder scored **20/20 against the baseline's
#: 19/20** — a better score — while moving 11 of 20 verdicts and pulling eight
#: separate cases onto the identical answer, "BUY 75". Measured concentration
#: was 25% with the reorder off and 40% with it on, so the threshold sits
#: between the two rather than at a round number chosen by taste.
#:
#: Why it is worth failing a run over: this app's claim is "read the spread,
#: not the average". Eight investors agreeing to the point is not agreement,
#: it is the lens being ignored — and every per-case grader is blind to it,
#: because each answer is individually well-formed.
MAX_VERDICT_SHARE = 0.35


def _verdict_concentration(rows: list[dict]) -> tuple[float, str]:
    """Share of cases landing on the single most common (stance, conviction).

    Deliberately exact-match on the pair. Two investors reaching BUY from
    different convictions is judgement; two reaching the same number to the
    point, repeatedly, across different companies, is not.
    """
    verdicts = [
        f"{r.get('stance')} {r.get('conviction')}"
        for r in rows
        if r.get("stance") and r.get("conviction") is not None
    ]
    if not verdicts:
        return 0.0, "-"
    verdict, count = Counter(verdicts).most_common(1)[0]
    return count / len(verdicts), verdict


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _failed(case: Case, reason: str, ms: int) -> dict:
    """A case that never produced an answer fails every check it carried.

    Not skipped, and not silently absent from the score — an unanswered case is
    a failed case, or a broken provider reads as a clean run.
    """
    return {
        "id": case.id,
        "category": case.category,
        "persona": case.persona,
        "fixture": case.fixture,
        "error": reason,
        "checks": [{"name": n, "passed": False, "reason": reason} for n, _ in case.checks],
        "ms": ms,
        "tokens_in": None,
        "tokens_out": None,
    }


async def run_case(case: Case, model: str | None) -> dict:
    """Score one case by running the *shipped* analysis path.

    Deliberately `run_research_analysis`, not a prompt assembled here. The
    first version of this file built its own prompt — persona style plus a raw
    dump of the snapshot — and scored that. It was roughly half of the real
    prompt: no methodology notes, no metric catalog, no context manifest, no
    verifier, and none of `_analyze`'s assembly.

    That was not merely less faithful, it was inert. The `llm_shared_prefix`
    reorder lives inside `_analyze`, so the flag could not reach a prompt built
    out here: hashing the assembled prompt with the flag off and on gave the
    same sha256, and a 20-case run therefore reported "no verdict changed"
    while comparing a prompt to itself. The committee path, which does go
    through `_analyze`, moved Burry from SELL 15 to BUY 85 on the same
    snapshot. An eval that scores a lookalike of the prompt tells you nothing
    about the prompt.
    """
    snapshot = fixtures.load(case.fixture)
    # The synthetic fixtures carry ticker TEST; the captured ones are named for
    # their ticker. Either way the app's own guardrail sees a real symbol.
    ticker = str(snapshot.get("ticker") or case.fixture)
    bundle = json.dumps(snapshot, indent=1, default=str)

    t0 = time.perf_counter()
    try:
        out = await run_research_analysis(ticker, snapshot, persona_id=case.persona, persist=False)
    except Exception as exc:  # noqa: BLE001
        return _failed(case, f"{type(exc).__name__}: {str(exc)[:120]}", _ms(t0))
    ms = _ms(t0)

    if "error" in out:
        return _failed(case, f"{out['error']}: {str(out.get('message'))[:100]}", ms)

    answer = out.get("analysis")
    if not isinstance(answer, dict):
        return _failed(case, "no analysis in response", ms)

    ctx = {"snapshot_text": bundle, "persona": case.persona, **case.ctx}
    checks = []
    for name, grader in case.checks:
        try:
            v = grader(answer, ctx)
            checks.append({"name": name, "passed": v.passed, "reason": v.reason})
        except Exception as exc:  # noqa: BLE001
            # A grader that raises is a broken grader, and that is a failure of
            # the harness, not of the model. Say which.
            checks.append({"name": name, "passed": False, "reason": f"GRADER ERROR: {exc}"})

    usage = out.get("usage") or {}
    return {
        "id": case.id,
        "category": case.category,
        "persona": case.persona,
        "fixture": case.fixture,
        "stance": answer.get("stance"),
        "conviction": answer.get("conviction_score"),
        "checks": checks,
        "ms": ms,
        "tokens_in": usage.get("prompt_tokens"),
        "tokens_out": usage.get("completion_tokens"),
        "model": out.get("model"),
        # The app's own verifier ran too; record whether it objected, so a
        # grounding regression the graders miss is still visible in the record.
        "verification": (out.get("verification") or {}).get("status"),
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capture", action="store_true", help="freeze the real snapshots, then exit")
    ap.add_argument("--case", action="append", help="run only these case ids; repeatable")
    ap.add_argument("--model", default=None, help="override the model for every call")
    ap.add_argument("--label", default="", help="a note stored with the results")
    args = ap.parse_args()

    if args.capture:
        print(f"capturing {len(fixtures.CAPTURE)} snapshots into {fixtures.DIR}")
        return await capture()

    cases = [c for c in CASES if not args.case or c.id in set(args.case)]
    if not cases:
        print(f"no case matched {args.case}; known ids:")
        for c in CASES:
            print(f"  {c.id}")
        return 2

    missing = sorted({c.fixture for c in cases} - set(fixtures.available()))
    if missing:
        print(f"missing fixtures: {missing}\nRun with --capture first.")
        return 2

    # The shipped path reads the model from settings rather than taking it as an
    # argument, so an override has to be applied there. Done once, before any
    # case runs, so every row in a result file is from the same model.
    if args.model:
        settings.ollama_model = args.model

    print(f"golden set: {len(cases)} cases, model={args.model or 'configured default'}\n")
    started = time.time()
    rows = [await run_case(c, args.model) for c in cases]

    for r in rows:
        failed = [c for c in r["checks"] if not c["passed"]]
        mark = "PASS" if not failed else "FAIL"
        cv = r.get("conviction")
        head = (
            f"  {mark}  {r['id']:<34} {str(r.get('stance') or '-'):5s} "
            f"{(str(cv) if cv is not None else '-'):>4}"
        )
        print(f"{head}  {r['ms']:>6}ms")
        for c in failed:
            print(f"          └─ {c['name']}: {c['reason']}")

    passed = sum(1 for r in rows if all(c["passed"] for c in r["checks"]))
    checks_total = sum(len(r["checks"]) for r in rows)
    checks_passed = sum(1 for r in rows for c in r["checks"] if c["passed"])
    tin = sum(r["tokens_in"] or 0 for r in rows)
    tout = sum(r["tokens_out"] or 0 for r in rows)
    by_cat = Counter(r["category"] for r in rows if all(c["passed"] for c in r["checks"]))
    cat_totals = Counter(r["category"] for r in rows)

    concentration, top_verdict = _verdict_concentration(rows)
    homogenised = concentration > MAX_VERDICT_SHARE

    print()
    print(f"  cases  {passed}/{len(rows)} passed")
    print(f"  checks {checks_passed}/{checks_total} passed")
    for cat in sorted(cat_totals):
        print(f"    {cat:<12} {by_cat[cat]}/{cat_totals[cat]}")
    flag = "  <-- LENS COLLAPSE" if homogenised else ""
    print(
        f"  spread {concentration:.0%} of cases on {top_verdict!r} (max {MAX_VERDICT_SHARE:.0%}){flag}"
    )
    print(f"  wall   {time.time() - started:.0f}s")
    print(f"  tokens {tin:,} in / {tout:,} out")
    # The local model is free; the figure that matters is what this would bill
    # hosted, because that is the number that decides whether it can run often.
    print(f"  cost   $0.00 local  ·  ${tin / 1e6 * 5 + tout / 1e6 * 25:.4f} at $5/$25 per MTok")

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS / f"{stamp}.json"
    out.write_text(
        json.dumps(
            {
                "when": stamp,
                "label": args.label,
                "model": rows[0].get("model") if rows else None,
                "cases_passed": passed,
                "cases_total": len(rows),
                "checks_passed": checks_passed,
                "checks_total": checks_total,
                "tokens_in": tin,
                "tokens_out": tout,
                # Recorded so two runs can be compared on spread, not just on
                # score. The reorder comparison needed exactly this.
                "verdict_concentration": round(concentration, 3),
                "top_verdict": top_verdict,
                "lens_collapse": homogenised,
                "shared_prefix": settings.llm_shared_prefix,
                "rows": rows,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\n  recorded -> {out.relative_to(ROOT)}")
    # A scoring tool that always exits 0 is one nobody notices failing — the
    # same objection the graders themselves are built around.
    return 0 if passed == len(rows) and not homogenised else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
