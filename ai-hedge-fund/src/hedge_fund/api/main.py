"""FastAPI application — AI hedge fund dashboard API."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi import status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from hedge_fund.api.routes import (
    autoresearch,
    backtest,
    breadth,
    decisions,
    constraints,
    knowledge,
    data,
    factors,
    macro,
    membership as membership_route,
    methodology,
    optimize as optimize_route,
    portfolio,
    regimes,
    research,
    runs,
    screeners,
    setup as setup_route,
    simulation,
    valuation,
)
from hedge_fund.api.membership import MemberGateMiddleware
from hedge_fund.members.ledger import BudgetExhausted
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
    # Under /api, because the frontend owns `/docs`.
    #
    # FastAPI's default puts Swagger UI at `/docs`, and this app serves its own
    # reference section there — the one that labels every capability `computed`,
    # `chosen-then-computed`, `written` or `judged`. Registered first, the
    # framework's route won: on the deployed site `/docs` returned Swagger and
    # the reference section was unreachable, which made the page that explains
    # what to trust the one page nobody could read.
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Invite-only gate. Registered BEFORE CORS on purpose, and the ordering is the
# opposite of what it looks like: `add_middleware` does `insert(0, ...)`, so the
# middleware added *last* ends up outermost. Adding the gate first therefore
# leaves CORS wrapping it, which is what makes the gate's 401 carry its
# `Access-Control-Allow-Origin` header.
#
# Getting this backwards is silent and nasty. The gate still refuses, but the
# refusal reaches an off-origin browser as an opaque network error instead of a
# 401 — so `api.ts` never parses the typed reason, `MemberGate` falls into its
# "transport problem" branch, and the app renders as though there were no gate
# at all. Same-origin deployments never notice. See `test_membership.py`.
app.add_middleware(MemberGateMiddleware)

# CORS for frontend
frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Membership first, and unprefixed: /api/join, /api/me and /api/logout are the
# three paths that have to stay reachable without a session, because they are
# how one is obtained and how a client learns it has not got one. The gate
# exempts exactly these plus /api/health.
app.include_router(membership_route.router, prefix="/api", tags=["membership"])

app.include_router(data.router, prefix="/api/data", tags=["data"])
app.include_router(research.router, prefix="/api/research", tags=["research"])
app.include_router(valuation.router, prefix="/api/valuation", tags=["valuation"])
app.include_router(simulation.router, prefix="/api/simulation", tags=["simulation"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(screeners.router, prefix="/api/screeners", tags=["screeners"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])
app.include_router(optimize_route.router, prefix="/api/optimize", tags=["optimize"])
app.include_router(runs.router, prefix="/api/runs", tags=["runs"])
app.include_router(methodology.router, prefix="/api/methodology", tags=["methodology"])
app.include_router(setup_route.router, prefix="/api/setup", tags=["setup"])
app.include_router(autoresearch.router, prefix="/api/autoresearch", tags=["autoresearch"])
app.include_router(decisions.router, prefix="/api/decisions", tags=["decisions"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(constraints.router, prefix="/api/constraints", tags=["constraints"])
app.include_router(factors.router, prefix="/api/factors", tags=["factors"])
app.include_router(macro.router, prefix="/api/macro", tags=["macro"])
app.include_router(regimes.router, prefix="/api/regimes", tags=["regimes"])
app.include_router(breadth.router, prefix="/api/breadth", tags=["breadth"])


@app.exception_handler(BudgetExhausted)
async def _budget_exhausted(request, exc: BudgetExhausted):
    """A fan-out that ran out part-way through answers like the door check.

    Same status and same `reason` as `require_budget`, so the client needs one
    branch rather than two for what is one situation reached two ways.
    """
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": {
                "reason": "budget_exhausted",
                "message": str(exc),
                "tokens": exc.spent,
                "cap": exc.cap,
            }
        },
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.3.0"}


_static_dir = os.environ.get("STATIC_DIR") or os.environ.get("FRONTEND_DIST")
if _static_dir:
    _p = Path(_static_dir)
    if _p.is_dir():
        from starlette.exceptions import HTTPException as StarletteHTTPException
        from starlette.responses import FileResponse
        from starlette.staticfiles import StaticFiles

        class SPAStaticFiles(StaticFiles):
            """Serve the built frontend, and hand unknown paths to the router.

            `StaticFiles(html=True)` answers an unknown path with `404.html` if
            one exists, and the frontend ships one — for GitHub Pages, where a
            static host cannot route `/dashboard` to `index.html` and the
            documented workaround is a 404 page that re-enters through a query
            parameter. Served from here instead, that workaround looped: its
            `segmentCount = 1` assumes the app lives one path segment deep
            (`/ai-hedge-fund/`, the repo name), so at a domain root it rewrote
            `/dashboard` to `/dashboard/?p=/`, 404'd again, and appended
            another `~and~q=p=/` on every pass. Roughly a thousand requests per
            page load, a growing URL, and a blank screen — and every deep link
            on the deployed site was affected.

            A real server does not need that trick: it can return `index.html`
            with a 200 and let the client router read the path. So unknown
            paths fall back to the entry point, which is what makes a shared
            link to `/screeners` work at all.

            Kept narrow deliberately. A missing *asset* must stay a 404: a
            mistyped script or font that silently returns HTML turns a build
            problem into a baffling parse error. And anything under `/api`
            belongs to the router, so a wrong endpoint keeps answering 404
            rather than a page.
            """

            def _is_route(self, path: str) -> bool:
                """A client-side route, as opposed to an asset or an endpoint.

                A path with a file extension is an asset: a mistyped script or
                font must keep 404ing rather than quietly returning HTML, which
                turns a build problem into a parse error somewhere else. `/api`
                belongs to the router.
                """
                return not Path(path).suffix and not path.startswith("api/")

            async def get_response(self, path: str, scope):
                # `html=True` does not raise for an unknown path — it *returns*
                # `404.html` with a 404 status, which is how the GitHub Pages
                # shim got served and looped. So the response has to be
                # inspected, not just exceptions caught.
                try:
                    response = await super().get_response(path, scope)
                except StarletteHTTPException as exc:
                    if exc.status_code == 404 and self._is_route(path):
                        return FileResponse(_p / "index.html", status_code=200)
                    raise
                if response.status_code == 404 and self._is_route(path):
                    return FileResponse(_p / "index.html", status_code=200)
                return response

        app.mount("/", SPAStaticFiles(directory=str(_p), html=True), name="static")
