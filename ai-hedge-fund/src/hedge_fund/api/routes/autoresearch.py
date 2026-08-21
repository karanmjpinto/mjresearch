"""Autoresearch — run the loop, and read what it found."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from hedge_fund.autoresearch import (
    describe_harness,
    leaderboard,
    list_experiments,
    run_loop,
    summarize,
)
from hedge_fund.data.service import get_data_service

logger = logging.getLogger(__name__)

router = APIRouter()
_ds = get_data_service()

# One loop at a time. Concurrent runs would interleave their trial counts, and
# the significance hurdle depends on knowing how many things were tried.
_running: dict[str, asyncio.Task] = {}


class LoopRequest(BaseModel):
    run_tag: str = Field(max_length=64, description="Groups experiments, e.g. 'aug21'")
    tickers: list[str] = Field(min_length=1, max_length=12)
    experiments: int = Field(default=10, ge=1, le=200)
    days: int = Field(default=1825, ge=400, le=7300)
    max_seconds: float | None = Field(default=None, ge=30, le=43200)


@router.get("/harness")
async def get_harness() -> dict[str, Any]:
    """The fixed evaluation rules every experiment is judged by."""
    return describe_harness()


@router.get("/experiments")
async def get_experiments(
    run_tag: str | None = None, limit: int = Query(default=100, ge=1, le=1000)
) -> dict[str, Any]:
    rows = list_experiments(run_tag=run_tag, limit=limit)
    return {"count": len(rows), "experiments": rows}


@router.get("/leaderboard")
async def get_leaderboard(
    run_tag: str | None = None, limit: int = Query(default=10, ge=1, le=50)
) -> dict[str, Any]:
    """Best out-of-sample results.

    Read alongside the trial count: the more experiments behind a number, the
    less a high one means on its own.
    """
    return {"leaderboard": leaderboard(run_tag=run_tag, limit=limit)}


@router.get("/summary/{run_tag}")
async def get_summary(run_tag: str) -> dict[str, Any]:
    return {**summarize(run_tag), "running": run_tag in _running}


@router.get("/status")
async def get_status() -> dict[str, Any]:
    return {"running": sorted(_running), "busy": bool(_running)}


@router.post("/run")
async def start_loop(req: LoopRequest, background: BackgroundTasks) -> dict[str, Any]:
    """Start a loop in the background and return immediately.

    A run of any length outlives an HTTP request, so results are read back from
    /experiments and /summary rather than awaited here.
    """
    if _running:
        raise HTTPException(
            status_code=409,
            detail=f"a loop is already running: {sorted(_running)}. Wait for it to finish.",
        )

    tag = req.run_tag.strip()
    if not tag:
        raise HTTPException(status_code=400, detail="run_tag must not be empty")

    async def _work() -> None:
        try:
            await run_loop(
                tag,
                req.tickers,
                data_service=_ds,
                experiments=req.experiments,
                days=req.days,
                max_seconds=req.max_seconds,
            )
        except Exception:
            logger.exception("Autoresearch loop %s failed", tag)
        finally:
            _running.pop(tag, None)

    _running[tag] = asyncio.create_task(_work())
    return {
        "started": True,
        "run_tag": tag,
        "experiments": req.experiments,
        "tickers": [t.upper() for t in req.tickers],
        "poll": f"/api/autoresearch/summary/{tag}",
    }
