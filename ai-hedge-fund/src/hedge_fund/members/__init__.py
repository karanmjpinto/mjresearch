"""Invite-only membership: who is let in, and what their model access costs.

`service` holds the data operations (mint, consume, revoke, resolve, spend) and
knows nothing about HTTP. `ledger` is the attribution hook the LLM client calls
after every model call, which is a no-op when nobody is logged in — that is how
a local checkout stays unmetered.
"""

from hedge_fund.members import ledger, service

__all__ = ["ledger", "service"]
