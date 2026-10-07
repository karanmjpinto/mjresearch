"""Attribution for model calls: who caused this, and what did it cost them.

The problem this solves is that a single API request fans out into many model
calls. One committee run is a call per persona plus a rebuttal round plus a
synthesis, and the thing that knows the member is the HTTP layer while the
thing that knows the token counts is the LLM client several frames below it.
Threading a member id down through `run_committee_analysis` into `call_json`
would mean changing every signature in between, and would be missed by the next
call site added.

So the member is carried in a `ContextVar` instead. The API layer opens a scope
for the duration of the request; `call_json` records against whatever scope is
open. `contextvars` are copied into tasks at creation, so an `asyncio.gather`
over seven personas inherits the scope without doing anything.

When no scope is open — which is every local run, every CLI invocation, every
test that does not ask for metering — `record` is a no-op and nothing is
written. That is how a local checkout stays unmetered: not by a flag, but
because nobody is logged in.
"""

from __future__ import annotations

import contextlib
import logging
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator

logger = logging.getLogger(__name__)


class BudgetExhausted(RuntimeError):
    """This member's monthly allowance ran out part-way through a fan-out.

    Raised from inside the model client rather than at the door, because the
    door is not where the spending happens. One request can be a committee of
    seven calls plus a rebuttal round, and `/api/autoresearch/run` is a
    detached task of up to two hundred experiments — all behind a single
    admission check. Checking only on the way in bounds the overshoot at
    "whatever one request can spend", which for the autoresearch loop is hours.
    """

    def __init__(self, spent: int, cap: int) -> None:
        super().__init__(f"Monthly allowance exhausted: {spent:,} of {cap:,} tokens used.")
        self.spent = spent
        self.cap = cap


@dataclass
class Attribution:
    """Who is spending, and how much they have left as of this request.

    Mutable, and deliberately so: `spent` is updated in place as the fan-out
    records calls, which is what lets a long run notice it has crossed the line
    without re-reading the database before every model call.
    """

    member_id: int
    #: The API route that caused the fan-out, not the model's own name. A
    #: committee run is many rows sharing one route.
    route: str
    #: Month-to-date tokens as of the moment this scope opened, plus everything
    #: recorded inside it since.
    spent: int = 0
    #: 0 means "not enforced here" — the gate is off, so nothing is metered.
    cap: int = 0


_current: ContextVar[Attribution | None] = ContextVar("llm_attribution", default=None)


@contextlib.contextmanager
def attribute_to(member_id: int, route: str, *, spent: int = 0, cap: int = 0) -> Iterator[None]:
    """Meter every model call made inside this block against one member."""
    token = _current.set(Attribution(member_id=member_id, route=route, spent=spent, cap=cap))
    try:
        yield
    finally:
        _current.reset(token)


def current() -> Attribution | None:
    return _current.get()


def check_budget() -> None:
    """Refuse the next model call if this scope has spent its allowance.

    Called by the model client before it dispatches, so a fan-out stops partway
    instead of running to completion on a member who ran out at call three.
    A no-op when nothing is being metered, which is every local run.

    The overshoot that remains is one call per *concurrent* request, because
    the count for a call only exists after it returns. That is a real bound,
    unlike the previous one.
    """
    attribution = _current.get()
    if attribution is None or attribution.cap <= 0:
        return
    if attribution.spent >= attribution.cap:
        raise BudgetExhausted(attribution.spent, attribution.cap)


def record(model: str, usage: dict[str, Any] | None) -> None:
    """Write one metered call, if anybody is being metered.

    Never raises. A failure to account for a call that already happened must
    not turn a successful analysis into an error response — the user would see
    a failure for work that was done and paid for. The row is lost and logged
    instead, which undercounts; the alternative loses the result, which is
    worse.
    """
    attribution = _current.get()
    if attribution is None:
        return

    prompt = (usage or {}).get("prompt_tokens") or 0
    completion = (usage or {}).get("completion_tokens") or 0
    cost = (usage or {}).get("cost")

    # Update the running total first and unconditionally. If the database write
    # below fails, the in-scope count must still reflect what was spent — the
    # alternative is that a member whose ledger writes are failing gets an
    # unlimited allowance for the rest of the request.
    attribution.spent += int(prompt) + int(completion)

    try:
        # Imported here, not at module scope: `llm.py` imports this module, and
        # the database session pulls in the ORM, which would make the LLM
        # client depend on the database at import time for no reason.
        from hedge_fund.db.session import SessionLocal
        from hedge_fund.members import service

        db = SessionLocal()
        try:
            service.record_usage(
                db,
                member_id=attribution.member_id,
                route=attribution.route,
                model=model,
                prompt_tokens=int(prompt),
                completion_tokens=int(completion),
                cost_usd=cost,
            )
        finally:
            db.close()
    except Exception:  # pragma: no cover - accounting must not break the call
        logger.exception(
            "could not record model usage for member %s on %s",
            attribution.member_id,
            attribution.route,
        )
