"""Reproducible research runs: content-addressed snapshots and persisted results."""

from hedge_fund.runs.hashing import canonical_json, run_key, snapshot_hash
from hedge_fund.runs.store import (
    RunRecord,
    compare_runs,
    get_run,
    get_snapshot,
    list_runs,
    save_run,
)

__all__ = [
    "RunRecord",
    "canonical_json",
    "compare_runs",
    "get_run",
    "get_snapshot",
    "list_runs",
    "run_key",
    "save_run",
    "snapshot_hash",
]
