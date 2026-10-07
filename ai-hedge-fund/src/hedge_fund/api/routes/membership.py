"""Join, identify, leave. The three routes that stay open behind the gate.

They have to be reachable without a session, because they are how a session is
obtained and how a client finds out it has not got one. Everything else under
`/api` is closed by `MemberGateMiddleware`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import Depends

from hedge_fund.api import guards, membership
from hedge_fund.db.session import get_db
from hedge_fund.members import service
from hedge_fund.settings import settings

router = APIRouter()


class JoinRequest(BaseModel):
    token: str = Field(min_length=8, max_length=256)


class JoinResponse(BaseModel):
    label: str
    tokens_this_month: int
    monthly_token_cap: int


class MeResponse(BaseModel):
    #: False when the gate is off, which is the local default. The client uses
    #: this to know whether to show membership at all — on a local checkout
    #: there is no door and a "you are a member" badge would be noise.
    gate_enabled: bool
    member: bool
    label: str | None = None
    is_owner: bool = False
    tokens_this_month: int = 0
    monthly_token_cap: int = 0
    #: Whether this deployment runs models for anyone at all. Separate from the
    #: budget: a member with tokens left still cannot run anything if the
    #: deployment has opted out.
    llm_enabled: bool = False


@router.post("/join", response_model=JoinResponse)
async def join(
    payload: JoinRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> JoinResponse:
    """Spend an invite and become a member.

    Rate-limited per IP under its own namespace. Without the limit this is a
    token-guessing oracle regardless of how long the token is; without the
    namespace, join attempts and model runs would share one hourly bucket, so
    clicking an invite link twice would eat the member's own model allowance
    and a brute-forcer could exhaust the allowance of everyone behind the same
    NAT. Keyed on `trusted_client_ip` rather than the usual helper, because
    here the limit is the security control and the usual helper reads a header
    the caller can forge.
    """
    limit = settings.member_join_attempts_per_hour
    if limit > 0:
        over, retry = guards.over_limit(f"join:{guards.trusted_client_ip(request)}", limit)
        if over:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "reason": "rate_limited",
                    "message": f"Too many attempts. Try again in {retry}s.",
                },
                headers={"Retry-After": str(retry)},
            )

    try:
        member, secret = service.consume_invite(db, payload.token.strip())
    except service.InviteRejected as rejected:
        # 403, not 401: this is not "you are unauthenticated", it is "this
        # specific capability will not open". A 401 would make a browser think
        # credentials might help.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason": rejected.reason, "message": rejected.message},
        ) from rejected

    membership.set_session_cookie(response, secret, request)
    return JoinResponse(
        label=member.label,
        tokens_this_month=0,
        monthly_token_cap=member.llm_monthly_token_cap,
    )


@router.get("/me", response_model=MeResponse)
async def me(request: Request, db: Session = Depends(get_db)) -> MeResponse:
    """Who you are, and what you have left.

    Deliberately 200-with-`member: false` rather than 401. The client calls
    this on every load to decide which screen to render, and an error status
    for the ordinary case of "not logged in yet" makes that a thrown exception
    in the query layer for something that is not an error.
    """
    member = service.resolve_session(db, request.cookies.get(membership.COOKIE_NAME))
    if member is None:
        return MeResponse(
            gate_enabled=settings.member_gate_enabled,
            member=False,
            llm_enabled=settings.llm_endpoints_enabled,
        )

    spend = service.spend_for(db, member)
    return MeResponse(
        gate_enabled=settings.member_gate_enabled,
        member=True,
        label=member.label,
        is_owner=member.is_owner,
        tokens_this_month=spend.tokens,
        monthly_token_cap=spend.cap,
        llm_enabled=settings.llm_endpoints_enabled,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, db: Session = Depends(get_db)) -> Response:
    """Revoke this session. Idempotent, and silent about whether there was one.

    The response is built here rather than taking the injected `Response` and
    returning a fresh one — doing that discards every header set on the
    injected object, so the cookie would be revoked server-side while the
    browser kept holding a dead one.
    """
    service.close_session(db, request.cookies.get(membership.COOKIE_NAME))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    membership.clear_session_cookie(response)
    return response
