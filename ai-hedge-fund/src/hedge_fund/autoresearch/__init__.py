"""Autonomous research loop: propose, evaluate on fixed rules, keep or discard."""

from hedge_fund.autoresearch.harness import (
    Evaluation,
    HarnessError,
    describe_harness,
    evaluate,
    split_history,
    trials_adjusted_hurdle,
)
from hedge_fund.autoresearch.loop import Hypothesis, propose, run_baseline, run_loop
from hedge_fund.autoresearch.store import (
    leaderboard,
    list_experiments,
    summarize,
    trial_count,
)

__all__ = [
    "Evaluation",
    "HarnessError",
    "Hypothesis",
    "describe_harness",
    "evaluate",
    "leaderboard",
    "list_experiments",
    "propose",
    "run_baseline",
    "run_loop",
    "split_history",
    "summarize",
    "trial_count",
    "trials_adjusted_hurdle",
]
