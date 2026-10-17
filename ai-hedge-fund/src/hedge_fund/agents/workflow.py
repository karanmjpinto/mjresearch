"""The committee's contract and hop values, as one object instead of four constants.

A committee run is shaped by a few values that were, until now, scattered
literals: how wide a conviction spread counts as a material split, how many
distinct stances do, what the analysts are told in the rebuttal round, and what
the portfolio manager is told when reconciling them. Changing any of them meant
editing code, which made the one question worth asking — did the change make
the committee better or worse — impossible to put on a fixed input.

This object carries only those values. It is deliberately not a general
workflow language: no roles, no persona prose, no ordering of stages. The
default instance reproduces the shipped behaviour byte for byte, and
`tests/test_committee_workflow.py` holds it to that, so passing no workflow and
passing the default are the same run.

A challenger is a JSON file overriding some fields; see
`scripts/run_committee_ab.py` for the only thing that reads one.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from hedge_fund.agents.personas import REBUTTAL_RULES, SYNTHESIS_SYSTEM


class CommitteeWorkflow(BaseModel):
    """What a committee run is held to, beyond the personas themselves."""

    # Frozen so one instance can be shared across a fan-out; `forbid` so a
    # misspelt field in a challenger file fails loudly instead of silently
    # comparing the default to itself.
    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Hop. A conviction spread at or above this routes to a rebuttal round.
    dissent_spread_threshold: int = Field(default=30, ge=0, le=100)
    #: Hop. More distinct stances than this also routes to a rebuttal round.
    dissent_max_stances: int = Field(default=2, ge=1, le=4)
    #: Contract. Appended to each persona's own system prompt in the rebuttal.
    rebuttal_rules: str = Field(default=REBUTTAL_RULES, min_length=1)
    #: Contract. The portfolio manager's system prompt for the synthesis.
    synthesis_system: str = Field(default=SYNTHESIS_SYSTEM, min_length=1)

    def changed_fields(self) -> list[str]:
        """Names of the fields that differ from the shipped default."""
        default = CommitteeWorkflow()
        return [
            name
            for name in type(self).model_fields
            if getattr(self, name) != getattr(default, name)
        ]


DEFAULT_WORKFLOW = CommitteeWorkflow()


def load_workflow(path: str | Path) -> CommitteeWorkflow:
    """Read a challenger: a JSON object overriding some fields of the default."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("a workflow file must hold one JSON object")
    return CommitteeWorkflow(**raw)
