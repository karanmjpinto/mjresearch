"""Compare the current committee with a changed one, on the frozen fixtures.

    uv run python scripts/run_committee_ab.py challenger.json
    uv run python scripts/run_committee_ab.py challenger.json --fixture KSS --fixture AAPL
    uv run python scripts/run_committee_ab.py challenger.json --persona warren_buffett \\
        --persona michael_burry --persona ben_graham

A challenger is a JSON object overriding some of the committee's contract and
hop values (see `hedge_fund.agents.workflow.CommitteeWorkflow`):

    {"dissent_spread_threshold": 20,
     "rebuttal_rules": "You have already given your view. ..."}

Both committees read the same snapshot. Both answers go through the hard gate
(numeric verifier, golden-set graders). Only when both clear it is one model
asked which is better, with the two shown as "Answer A" and "Answer B" in a
random order. A side that fails the gate is reported as failed and never
reaches the model.

What this is not: a search, an optimiser, or a verdict. It changes nothing in
the app. The preference column is a model's opinion with no outcome behind it;
read the reason, then decide.

This is not CI. It runs two full committees per fixture against the live model.
The gate and the unblinding are unit-tested in `tests/test_committee_ab.py`.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from evals import committee_ab, fixtures  # noqa: E402
from hedge_fund.agents.personas import DEFAULT_COMMITTEE_PERSONAS, is_valid_persona  # noqa: E402
from hedge_fund.agents.workflow import load_workflow  # noqa: E402

RESULTS = ROOT / "evals" / "results"


async def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("challenger", help="JSON file overriding committee workflow fields")
    ap.add_argument("--fixture", action="append", help="compare on these only; repeatable")
    ap.add_argument("--persona", action="append", help="committee members; repeatable")
    ap.add_argument("--seed", type=int, default=None, help="fixes which side is shown as A")
    ap.add_argument("--label", default="", help="a note stored with the results")
    args = ap.parse_args()

    try:
        challenger = load_workflow(args.challenger)
    except Exception as exc:  # noqa: BLE001
        print(f"cannot read challenger {args.challenger}: {exc}")
        return 2

    changed = challenger.changed_fields()
    if not changed:
        # The eval once reported "no verdict changed" while comparing a prompt
        # to itself. Refuse the same mistake here.
        print("the challenger is identical to the current workflow; nothing to compare")
        return 2

    names = args.fixture or committee_ab.captured_fixtures()
    unknown = sorted(set(names) - set(fixtures.available()))
    if unknown or not names:
        print(f"unknown or missing fixtures: {unknown}; available: {fixtures.available()}")
        return 2

    personas = args.persona or list(DEFAULT_COMMITTEE_PERSONAS)
    bad = [p for p in personas if not is_valid_persona(p)]
    if bad:
        print(f"unknown personas: {bad}")
        return 2

    seed = args.seed if args.seed is not None else secrets.randbelow(2**31)
    print(
        f"committee A/B: {len(names)} fixtures, {len(personas)} personas, "
        f"changed: {', '.join(changed)}\n"
    )
    started = time.time()
    rows = await committee_ab.compare(challenger, names, personas, seed=seed)

    print(committee_ab.render_table(rows))
    s = committee_ab.summarize(rows)
    print()
    print(
        f"  judged {s['judged']}/{s['fixtures']}  ·  prefers challenger {s['prefers_challenger']}"
        f"  ·  prefers current {s['prefers_current']}  ·  tie {s['tie']}"
    )
    print(
        f"  failed the gate: current {s['current_failed_gate']}, "
        f"challenger {s['challenger_failed_gate']}"
    )
    print(f"  wall   {time.time() - started:.0f}s  ·  seed {seed}")
    print("  The preference is one model's opinion. No outcome signal is behind it.")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS / f"ab-{stamp}.json"
    committee_ab.write_result(
        out,
        stamp=stamp,
        label=args.label,
        challenger=challenger,
        challenger_file=str(args.challenger),
        persona_ids=personas,
        seed=seed,
        rows=rows,
    )
    print(f"\n  recorded -> {out.relative_to(ROOT)}")
    # Non-zero only for the hard fact: the change broke the gate somewhere.
    # A preference, either way, is not a failure.
    return 1 if s["challenger_failed_gate"] else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
