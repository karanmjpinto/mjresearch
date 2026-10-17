"""The plan eval's yardstick: its question set and its arithmetic.

The eval itself needs a model and is not CI. What it measures against does
not, and a yardstick that drifts makes every later number meaningless.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.plan_questions import CAPABILITIES, QUESTIONS, coverage, covered  # noqa: E402
from hedge_fund.plan import get_metric  # noqa: E402


def _script():
    spec = importlib.util.spec_from_file_location(
        "run_plan_eval", ROOT / "scripts" / "run_plan_eval.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_every_capability_names_a_real_metric_or_none():
    """A tag pointing at a renamed metric would count as covered and compute nothing."""
    for cap, metric in CAPABILITIES.items():
        if metric is not None:
            assert get_metric(metric), f"{cap} names unknown metric {metric}"


def test_every_question_needs_only_known_capabilities():
    for q in QUESTIONS:
        unknown = [n for n in q.needs if n not in CAPABILITIES]
        assert not unknown, f"{q.id} needs undeclared capabilities {unknown}"
        assert q.needs, f"{q.id} declares no needs, so it is covered by nothing"


def test_question_ids_are_unique_and_tickers_are_frozen_fixtures():
    from evals import fixtures

    assert len({q.id for q in QUESTIONS}) == len(QUESTIONS)
    assert {q.ticker for q in QUESTIONS} <= set(fixtures.CAPTURE)


def test_coverage_counts_a_question_only_when_every_need_is_met():
    cov = coverage()
    assert cov["covered"] == sum(1 for q in QUESTIONS if covered(q))
    assert 0 < cov["share"] <= 1


def test_agreement_is_the_share_matching_the_most_common_result():
    agreement = _script().agreement
    assert agreement(["a", "a", "a", "b", "a"]) == 0.8
    assert agreement(["x"] * 5) == 1.0
    assert agreement([]) == 0.0
