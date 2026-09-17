"""Access control for the four endpoints that can spend money.

Everything else this API serves is computed locally from cached data and costs
nothing to call. Four routes are different, because they invoke a language
model:

    POST /api/research/check        one ticker, one committee
    POST /api/research/plan         the plan pipeline
    POST /api/simulation/backtest   a committee per bar — the expensive one
    POST /api/autoresearch/run      a loop, which is worse than expensive

Locally that is free: the default provider is Ollama on 127.0.0.1 and the only
cost is your own GPU. On the hosted deployment it is not. There
`llm_provider=openai` points at an OpenRouter key, so every one of those calls
bills the site's owner, and CORS does not help — it constrains browsers, and
`curl` has never read a CORS header in its life. An unauthenticated deployment
of those four routes is an anonymous LLM proxy with somebody's card behind it.

Three independent controls, because they answer different questions:

  - `llm_endpoints_enabled=False` — "this deployment does not do that at all".
    The honest setting for a public site whose landing page already promises
    the analysis runs on your own machine. Refuses before any key check, so a
    leaked key cannot re-enable it.
  - `llm_access_key` — "only I may spend it". Checked in constant time.
  - `llm_rate_limit_per_hour` — "and not even I may spend it in a loop".
    Bounds the damage from a key that has leaked, which is the case a key
    alone does nothing about.

All three default to off/unset, so a local checkout behaves exactly as before:
free model, no key, no limit.
"""

from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque

from fastapi import Depends, Header, HTTPException, Request, status

from hedge_fund.settings import settings

#: Per-client request timestamps, newest last. In memory and therefore
#: per-process: a multi-replica deployment limits per replica, and a restart
#: forgets. Both are acceptable here because this is a spend brake rather than
#: a security boundary — the key is the boundary. A shared counter would mean
#: Redis, which is a dependency this app does not otherwise need.
_hits: dict[str, deque[float]] = defaultdict(deque)

_WINDOW_S = 3600.0

#: Stop `_hits` growing without bound when many addresses each call once.
_MAX_TRACKED = 4096


def _client_ip(request: Request) -> str:
    """The caller as the edge saw them.

    Behind Railway and Cloudflare the socket address is the proxy, so every
    caller would share one bucket and the first visitor would exhaust it for
    everyone. `x-forwarded-for` is the client, and its first hop is the one the
    edge observed; later hops are proxy-supplied and not to be trusted.

    A client can forge this header when the app is exposed directly. That is
    the documented trade-off of trusting it: it is right behind a proxy that
    overwrites it, and forgeable without one. Since the limit is a spend brake
    and not the access boundary, per-IP accuracy is not load-bearing.
    """
    fwd = request.headers.get("x-forwarded-for", "")
    first = fwd.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client else "unknown"


def _over_limit(ip: str, limit: int) -> tuple[bool, int]:
    """Record this call and say whether it exceeded the hourly limit.

    Returns (over, retry_after_seconds).
    """
    now = time.monotonic()
    bucket = _hits[ip]
    cutoff = now - _WINDOW_S
    while bucket and bucket[0] < cutoff:
        bucket.popleft()

    if len(bucket) >= limit:
        retry = int(bucket[0] + _WINDOW_S - now) + 1
        return True, max(retry, 1)

    bucket.append(now)
    if len(_hits) > _MAX_TRACKED:
        # Drop the buckets that have gone quiet rather than every bucket, so a
        # flood of one-shot addresses cannot evict an active limiter's history.
        for k in [k for k, v in _hits.items() if not v or v[-1] < cutoff]:
            del _hits[k]
    return False, 0


async def require_llm_access(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Gate one model-invoking request. Raises, or returns None.

    Order matters. "Disabled" is checked first so that a deployment which has
    opted out cannot be talked past with a key, and the rate limit is checked
    last so a rejected caller does not consume another caller's allowance.
    """
    if not settings.llm_endpoints_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "This deployment does not run model analysis. It needs a local "
                "backend and Ollama — nothing about your book or your model "
                "leaves your computer, which is the point. Clone the repo and "
                "run it locally to use this."
            ),
        )

    expected = settings.llm_access_key
    if expected:
        # compare_digest rather than == so a wrong key cannot be recovered a
        # character at a time from response timing.
        if not x_api_key or not secrets.compare_digest(x_api_key, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Model analysis on this deployment requires a valid X-API-Key.",
                headers={"WWW-Authenticate": "X-API-Key"},
            )

    limit = settings.llm_rate_limit_per_hour
    if limit > 0:
        over, retry = _over_limit(_client_ip(request), limit)
        if over:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit reached: {limit} model runs per hour. Retry in {retry}s.",
                headers={"Retry-After": str(retry)},
            )


#: Attach to a route with `dependencies=[LLM_ACCESS]`, which leaves the
#: endpoint's own signature alone.
LLM_ACCESS = Depends(require_llm_access)


def reset_rate_limits() -> None:
    """Clear the counters. For tests, and for a deliberate manual reset."""
    _hits.clear()
