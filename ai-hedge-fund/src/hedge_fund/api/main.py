"""FastAPI application — AI hedge fund dashboard API."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hedge_fund.api.routes import (
    autoresearch,
    backtest,
    data,
    methodology,
    optimize as optimize_route,
    portfolio,
    research,
    runs,
    screeners,
    setup as setup_route,
    simulation,
)
from hedge_fund.db.session import init_db
from hedge_fund.settings import settings

if settings.sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        traces_sample_rate=settings.sentry_traces_sample_rate,
        environment=settings.sentry_environment,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AI Hedge Fund API",
    version="0.3.0",
    description="Market data, portfolio DB, weighted risk, and LLM research",
    lifespan=lifespan,
)

# CORS for frontend
frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data.router, prefix="/api/data", tags=["data"])
app.include_router(research.router, prefix="/api/research", tags=["research"])
app.include_router(simulation.router, prefix="/api/simulation", tags=["simulation"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(screeners.router, prefix="/api/screeners", tags=["screeners"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])
app.include_router(optimize_route.router, prefix="/api/optimize", tags=["optimize"])
app.include_router(runs.router, prefix="/api/runs", tags=["runs"])
app.include_router(methodology.router, prefix="/api/methodology", tags=["methodology"])
app.include_router(setup_route.router, prefix="/api/setup", tags=["setup"])
app.include_router(autoresearch.router, prefix="/api/autoresearch", tags=["autoresearch"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.3.0"}


_static_dir = os.environ.get("STATIC_DIR") or os.environ.get("FRONTEND_DIST")
if _static_dir:
    _p = Path(_static_dir)
    if _p.is_dir():
        from starlette.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(_p), html=True), name="static")
