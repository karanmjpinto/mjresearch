"""The HTTP side of membership: the cookie, the gate, and the budget.

Three pieces, and the division matters:

- `require_member` answers "may you call this at all". Applied to every
  `/api/*` path by default, not to an enumerated list of routers — see
  `MemberGateMiddleware` for why that distinction is the whole point.
- `require_budget` answers "may you spend money doing it". Only on the four
  model-invoking routes, because that is the only place spend happens.
- The cookie helpers keep the `Set-Cookie` flags in one place, since getting
  `HttpOnly`/`Secure`/`SameSite` subtly wrong is the usual way a session
  becomes stealable.

Both refusals carry a typed `reason` in the body. The rate limiter in `guards`
and the budget check both return 429, and "you are looping" and "you have spent
your month" need different responses from the client — one is worth retrying
after `Retry-After`, the other is not worth retrying at all this month.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from hedge_fund.db.models import Member
from hedge_fund.db.session import SessionLocal, get_db
from hedge_fund.members import ledger, service
from hedge_fund.settings import settings

#: Cookie name. Prefixed so it cannot collide with anything the static host or
#: Cloudflare sets.
COOKIE_NAME = "mj_session"

#: Paths reachable without a session, because they are how you get one or how
#: you find out you have not got one. Exact matches, not prefixes: a prefix
#: match on "/api/me" would also exempt "/api/members" if that ever existed.
PUBLIC_API_PATHS = frozenset(
    {
        "/api/health",
        "/api/join",
        "/api/me",
        "/api/logout",
    }
)


def _is_https(request: Request) -> bool:
    """Whether to mark the session cookie `Secure`.

    Configuration first, and that ordering is the point. An earlier version
    read `x-forwarded-proto`, which the client sets: a join request carrying
    `x-forwarded-proto: http` to an origin reachable without the edge — the
    `*.up.railway.app` host behind Cloudflare, say — would mint a session
    cookie with no `Secure` flag, which the browser then sends over plain HTTP.
    A security flag must not be decided by the party it constrains.

    `member_cookie_secure` is True by default. It exists to be turned *off* for
    local development, because a `Secure` cookie is never returned over plain
    HTTP and the session would silently fail to stick on
    `http://localhost:5173` — the developer joins, gets a 200, and is treated
    as a stranger by every request after it. So: trust the setting, and fall
    back to the observed scheme only when nothing is configured either way.
    """
    if settings.member_cookie_secure is not None:
        return settings.member_cookie_secure
    return request.url.scheme == "https"


def set_session_cookie(response: Response, secret: str, request: Request) -> None:
    """Attach a session cookie with the flags that make it worth having.

    `httponly` so script cannot read it. `samesite=lax` so it is not sent on
    cross-site POSTs — which is what stands in for CSRF protection here; if
    this ever has to become `samesite=none` for an off-origin frontend, that
    protection is gone and a real CSRF token has to arrive in the same change.

    `secure` is conditional on the connection actually being HTTPS, and that is
    not a loosening. A `Secure` cookie is simply never sent back over plain
    HTTP, so hardcoding it would mean the session silently fails to stick on
    `http://localhost:5173` — the developer joins, gets a 200, and is then
    treated as a stranger by every subsequent request with nothing in the logs
    to explain it. Production is HTTPS at the edge, so the flag is set there,
    which is the only place it does anything.
    """
    response.set_cookie(
        COOKIE_NAME,
        secret,
        max_age=settings.member_session_days * 24 * 3600,
        httponly=True,
        secure=_is_https(request),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def current_member(request: Request, db: Session = Depends(get_db)) -> Member | None:
    """The member this request belongs to, or None. Never raises."""
    return service.resolve_session(db, request.cookies.get(COOKIE_NAME))


def require_member(request: Request, db: Session = Depends(get_db)) -> Member | None:
    """Refuse the request unless it carries a live session.

    Returns None rather than raising when the gate is off, which is the local
    default — so every route behaves exactly as it did before membership
    existed, and `request.state.member` is simply absent.
    """
    if not settings.member_gate_enabled:
        return None

    member = service.resolve_session(db, request.cookies.get(COOKIE_NAME))
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "reason": "not_a_member",
                "message": (
                    "This site is invite-only. Everything on the overview and "
                    "the reference section is open; the rest needs a link from "
                    "someone who is already in."
                ),
            },
        )
    request.state.member = member
    return member


MEMBER = Depends(require_member)


def require_budget(request: Request, db: Session = Depends(get_db)) -> None:
    """Refuse a model call when this member has spent their month.

    This is the check at the door, and on its own it is not enough: it runs
    once per request, while a request is a fan-out. A committee is a dozen
    calls and `/api/autoresearch/run` is a detached task of up to two hundred
    experiments, so a single admission here would license hours of spending.
    `meter_llm` therefore carries the cap into the attribution scope and
    `ledger.check_budget` re-checks before every model call, which is what
    actually bounds it.

    What remains is one call per *concurrent* request, because a call's token
    count only exists once it returns.

    Silent when the gate is off — a local run has no member and no budget.
    """
    if not settings.member_gate_enabled:
        return

    member = getattr(request.state, "member", None) or service.resolve_session(
        db, request.cookies.get(COOKIE_NAME)
    )
    if member is None:
        # require_member runs first and would already have refused. Reaching
        # here means the gate is on and this route was wired without it.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason": "not_a_member", "message": "This site is invite-only."},
        )

    spend = service.spend_for(db, member)
    if spend.exhausted:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "reason": "budget_exhausted",
                "message": (
                    f"You have used {spend.tokens:,} of your {spend.cap:,} tokens "
                    "for this month. The allowance resets at the start of the "
                    "next calendar month."
                ),
                "tokens": spend.tokens,
                "cap": spend.cap,
            },
        )


BUDGET = Depends(require_budget)


async def meter_llm(request: Request, db: Session = Depends(get_db)):
    """Check the budget, then meter everything the handler spends.

    One dependency rather than two because the pair is meaningless apart: a
    budget check with no accounting never fires, and accounting with no check
    never refuses.

    This is a `yield` dependency so the attribution scope is open for the
    duration of the handler, not just while the dependency runs. That is what
    lets a committee run — one route, a dozen model calls across an
    `asyncio.gather` — attribute every call without any of the intermediate
    functions knowing a member exists. `contextvars` are copied into tasks at
    creation, so the fan-out inherits the scope for free.

    Attach with `dependencies=[METERED]` alongside `LLM_ACCESS`. Off the hot
    path entirely when the gate is disabled.
    """
    if not settings.member_gate_enabled:
        yield
        return

    require_budget(request, db)
    member = getattr(request.state, "member", None) or service.resolve_session(
        db, request.cookies.get(COOKIE_NAME)
    )
    if member is None:  # pragma: no cover - require_budget already refused
        yield
        return

    # The route, not the full path: `/api/research/check` for any ticker, so
    # the ledger groups by what was run rather than by what it was run on.
    route = request.scope.get("root_path", "") + str(
        getattr(request.scope.get("route"), "path", request.url.path)
    )
    # Carry the cap and the month-to-date total into the scope so the model
    # client can refuse mid-fan-out. Without this the check at the door is the
    # only one there is, and one admitted request can spend without limit —
    # `/api/autoresearch/run` is a detached task of up to 200 experiments.
    spend = service.spend_for(db, member)
    with ledger.attribute_to(member.id, route, spent=spend.tokens, cap=spend.cap):
        yield


METERED = Depends(meter_llm)


class MemberGateMiddleware(BaseHTTPMiddleware):
    """Default-deny for `/api/*`, by path rather than by route list.

    The obvious implementation is `dependencies=[MEMBER]` on each
    `include_router` call. That was rejected on purpose. There are twenty-odd
    routers and the list would have to be extended every time one is added —
    which means it will be missed exactly when a new one lands, and a route
    that nobody remembered to gate is the hole this whole module exists to
    close. The `breadth` router was added on the same branch as this gate,
    which is the argument in miniature.

    Working on the path also closes `/api/docs`, `/api/redoc` and
    `/api/openapi.json`. Those are mounted by FastAPI itself rather than by a
    router, so no router-level dependency reaches them, and they publish the
    full shape of the API.

    `require_member` stays as a dependency too, so a handler can ask who the
    caller is. The middleware is the boundary; the dependency is the identity.
    """

    async def dispatch(self, request: Request, call_next):
        if not settings.member_gate_enabled:
            return await call_next(request)

        path = request.url.path.rstrip("/") or "/"
        if not path.startswith("/api") or path in PUBLIC_API_PATHS:
            return await call_next(request)

        # CORS preflight carries no cookies by design, so refusing it would
        # turn a cross-origin deployment's every request into an opaque
        # failure. The actual request behind it is still gated.
        if request.method == "OPTIONS":
            return await call_next(request)

        db = SessionLocal()
        try:
            member = service.resolve_session(db, request.cookies.get(COOKIE_NAME))
            if member is None:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        "detail": {
                            "reason": "not_a_member",
                            "message": (
                                "This site is invite-only. The overview and the "
                                "reference section are open to everyone; the rest "
                                "needs a link from someone who is already in."
                            ),
                        }
                    },
                )
        finally:
            db.close()

        return await call_next(request)
