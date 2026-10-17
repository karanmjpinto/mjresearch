"""A/B test for a committee change: same snapshot, hard gate, then an opinion.

The question this answers is the one that comes up every time a rebuttal rule
or a dissent threshold is edited: did that make the committee better or worse?
The golden set cannot say — it scores one persona at a time and tells you only
that an answer obeys its contract.

For each fixture, on the one frozen snapshot:

  1. run the current committee and the challenger;
  2. put both final answers through the hard gate — the app's own numeric
     verifier, and the golden set's graders;
  3. only if BOTH clear it, ask one model which answer is better
     (`evals/pairwise.py`, which is the only model judgement in this package).

A side that fails the gate is reported as failed and is never shown to the
evaluator: an answer that contradicts its own snapshot does not get to win on
prose. Nothing here searches, proposes, or applies a workflow. It prints a
table and writes a record; the person reading it decides.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from evals import fixtures, pairwise
from evals import graders as g
from evals.golden import BASELINE
from hedge_fund.agents.personas import DEFAULT_COMMITTEE_PERSONAS
from hedge_fund.agents.research_agent import run_committee_analysis
from hedge_fund.agents.workflow import DEFAULT_WORKFLOW, CommitteeWorkflow

#: The golden-set graders that apply to a committee's final answer. The
#: per-persona lens checks in `golden.CASES` do not: a synthesis has no lens.
COMMITTEE_GATE: tuple[tuple[str, g.Grader], ...] = BASELINE + (
    ("no-invented-figures", g.no_invented_magnitudes),
    ("admits-thin-data", g.low_confidence_on_thin_data),
)

#: Constructed fixtures whose whole point is that the data is not to be trusted.
THIN_FIXTURES = frozenset({"THIN", "CONTRADICTORY"})

Runner = Callable[..., Awaitable[dict[str, Any]]]
Judge = Callable[..., Awaitable[dict[str, Any]]]


def captured_fixtures() -> list[str]:
    """The real snapshots on disk — the default set to compare on."""
    return sorted(p.stem for p in fixtures.DIR.glob("*.json")) if fixtures.DIR.is_dir() else []


def gate(out: dict[str, Any], snapshot: dict[str, Any], *, thin_data: bool = False) -> dict:
    """Every hard check over one committee run. No model is involved.

    Returns ``{"passed", "checks", "answer"}``. ``answer`` is the synthesis the
    committee produced, or None when it produced none.
    """
    synth = out.get("synthesis") if isinstance(out.get("synthesis"), dict) else {}
    answer = synth.get("analysis")
    if "error" in out or "error" in synth or not isinstance(answer, dict):
        err = out if "error" in out else synth
        reason = f"{err.get('error', 'no_analysis')}: {str(err.get('message'))[:120]}"
        return {
            "passed": False,
            "checks": [{"name": "committee-ran", "passed": False, "reason": reason}],
            "answer": None,
        }

    checks: list[dict[str, Any]] = [{"name": "committee-ran", "passed": True, "reason": ""}]

    # The verifier already ran inside the committee; read its verdict rather
    # than re-deriving it. A missing report fails — silence about a claim must
    # never look like a passing check.
    verification = synth.get("verification")
    if not isinstance(verification, dict) or not verification.get("status"):
        checks.append({"name": "verifier", "passed": False, "reason": "no verification report"})
    elif verification["status"] == "mismatch":
        n = verification.get("mismatched")
        checks.append(
            {
                "name": "verifier",
                "passed": False,
                "reason": f"{n} numeric claim(s) contradict the snapshot",
            }
        )
    else:
        checks.append({"name": "verifier", "passed": True, "reason": verification["status"]})

    ctx = {"snapshot_text": json.dumps(snapshot, indent=1, default=str), "thin_data": thin_data}
    for name, grader in COMMITTEE_GATE:
        try:
            v = grader(answer, ctx)
            checks.append({"name": name, "passed": v.passed, "reason": v.reason})
        except Exception as exc:  # noqa: BLE001
            checks.append({"name": name, "passed": False, "reason": f"GRADER ERROR: {exc}"})

    return {"passed": all(c["passed"] for c in checks), "checks": checks, "answer": answer}


def _side(out: dict[str, Any], gated: dict, ms: int) -> dict[str, Any]:
    answer = gated["answer"] or {}
    refinement = out.get("refinement") or {}
    return {
        "gate": "pass" if gated["passed"] else "fail",
        "failed_checks": [c for c in gated["checks"] if not c["passed"]],
        "checks": gated["checks"],
        "stance": answer.get("stance"),
        "conviction": answer.get("conviction_score"),
        "rebuttal_triggered": bool(refinement.get("triggered")),
        "answer": gated["answer"],
        "ms": ms,
    }


async def compare_fixture(
    name: str,
    challenger: CommitteeWorkflow,
    persona_ids: list[str],
    *,
    rng: random.Random,
    run: Runner = run_committee_analysis,
    judge: Judge = pairwise.judge,
) -> dict[str, Any]:
    """Both committees on one snapshot, gated, then judged if both survive."""
    snapshot = fixtures.load(name)
    ticker = str(snapshot.get("ticker") or name)
    thin = name in THIN_FIXTURES

    sides: dict[str, dict[str, Any]] = {}
    for label, workflow in (("current", DEFAULT_WORKFLOW), ("challenger", challenger)):
        t0 = time.perf_counter()
        try:
            out = await run(ticker, snapshot, persona_ids, workflow, persist=False)
        except Exception as exc:  # noqa: BLE001
            out = {"error": type(exc).__name__, "message": str(exc)}
        ms = int((time.perf_counter() - t0) * 1000)
        sides[label] = _side(out, gate(out, snapshot, thin_data=thin), ms)

    row: dict[str, Any] = {"fixture": name, "ticker": ticker, **sides}
    failed = [s for s in ("current", "challenger") if sides[s]["gate"] == "fail"]
    if failed:
        # The evaluator is not called. Not "called and ignored" — not called.
        row.update(
            judged=False,
            preference=None,
            reason=f"not judged: {' and '.join(failed)} failed the hard gate",
        )
        return row

    verdict = await judge(
        ticker, snapshot, sides["current"]["answer"], sides["challenger"]["answer"], rng=rng
    )
    if "error" in verdict:
        row.update(
            judged=False,
            preference=None,
            reason=f"evaluator failed: {verdict['error']}",
            evaluator=verdict,
        )
        return row
    row.update(
        judged=True, preference=verdict["preference"], reason=verdict["reason"], evaluator=verdict
    )
    return row


async def compare(
    challenger: CommitteeWorkflow,
    fixture_names: list[str],
    persona_ids: list[str] | None = None,
    *,
    seed: int,
    run: Runner = run_committee_analysis,
    judge: Judge = pairwise.judge,
) -> list[dict[str, Any]]:
    personas = list(persona_ids or DEFAULT_COMMITTEE_PERSONAS)
    rows = []
    for name in fixture_names:
        # Seeded per fixture so one fixture re-run alone draws the same labels.
        rng = random.Random(f"{seed}:{name}")
        rows.append(
            await compare_fixture(name, challenger, personas, rng=rng, run=run, judge=judge)
        )
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "fixtures": len(rows),
        "judged": sum(1 for r in rows if r["judged"]),
        "prefers_challenger": sum(1 for r in rows if r["preference"] == "challenger"),
        "prefers_current": sum(1 for r in rows if r["preference"] == "current"),
        "tie": sum(1 for r in rows if r["preference"] == "tie"),
        "current_failed_gate": sum(1 for r in rows if r["current"]["gate"] == "fail"),
        "challenger_failed_gate": sum(1 for r in rows if r["challenger"]["gate"] == "fail"),
    }


def _verdict(side: dict[str, Any]) -> str:
    if side["stance"] is None:
        return "-"
    return f"{side['stance']} {side['conviction']}"


def render_table(rows: list[dict[str, Any]]) -> str:
    """Gate result per side, preference, reason — one line per fixture."""
    head = f"  {'fixture':<14} {'current':<16} {'challenger':<16} {'prefers':<11} reason"
    lines = [head, "  " + "-" * (len(head) - 2)]
    for r in rows:
        cur, cha = r["current"], r["challenger"]
        lines.append(
            f"  {r['fixture']:<14} "
            f"{(cur['gate'].upper() + ' ' + _verdict(cur)):<16} "
            f"{(cha['gate'].upper() + ' ' + _verdict(cha)):<16} "
            f"{(r['preference'] or '-'):<11} "
            f"{' '.join(str(r['reason']).split())[:110]}"
        )
        for side in ("current", "challenger"):
            for c in r[side]["failed_checks"]:
                lines.append(f"  {'':<14} └─ {side} {c['name']}: {c['reason']}")
    return "\n".join(lines)


def write_result(
    path: Path,
    *,
    stamp: str,
    label: str,
    challenger: CommitteeWorkflow,
    challenger_file: str,
    persona_ids: list[str],
    seed: int,
    rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "kind": "committee_ab",
                "when": stamp,
                "label": label,
                "challenger_file": challenger_file,
                "changed_fields": challenger.changed_fields(),
                "challenger": challenger.model_dump(),
                "personas": persona_ids,
                "seed": seed,
                "summary": summarize(rows),
                "note": (
                    "preference is one model's opinion on two gated answers; "
                    "no outcome signal is behind it"
                ),
                "rows": rows,
            },
            indent=1,
            default=str,
        ),
        encoding="utf-8",
    )
