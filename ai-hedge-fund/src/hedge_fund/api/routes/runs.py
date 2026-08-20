"""Run history — inspect, compare, and replay past analyses."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from hedge_fund.runs import compare_runs, get_run, get_snapshot, list_runs

router = APIRouter()


@router.get("")
async def get_runs(
    ticker: str | None = None,
    mode: str | None = Query(default=None, description="single | persona | committee | plan"),
    run_key: str | None = Query(default=None, description="Only runs with identical inputs"),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """Recent runs, newest first. Snapshots are omitted; fetch one run for those."""
    runs = list_runs(ticker=ticker, mode=mode, run_key_filter=run_key, limit=limit)
    return {"count": len(runs), "runs": runs}


@router.get("/compare")
async def get_run_comparison(
    a: str = Query(description="First run uid"),
    b: str = Query(description="Second run uid"),
) -> dict[str, Any]:
    """Diff two runs.

    `nondeterminism_detected` is the field that matters: it means two runs with
    identical inputs reached different conclusions, so the pipeline is not yet
    reproducible and any eval built on it would be measuring noise.
    """
    result = compare_runs(a, b)
    if result.get("error") == "run_not_found":
        raise HTTPException(status_code=404, detail=f"run(s) not found: {result['missing']}")
    return result


@router.get("/snapshot/{snapshot_sha256}")
async def get_run_snapshot(snapshot_sha256: str) -> dict[str, Any]:
    """The exact market data a past analysis saw, for replay."""
    snapshot = get_snapshot(snapshot_sha256)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="snapshot not found")
    return snapshot


@router.get("/{run_uid}")
async def get_single_run(run_uid: str, include_snapshot: bool = True) -> dict[str, Any]:
    run = get_run(run_uid, include_snapshot=include_snapshot)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run
