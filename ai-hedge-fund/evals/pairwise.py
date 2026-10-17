"""MODEL JUDGEMENT LIVES HERE, and only here.

Everything else under `evals/` is a hard check: `graders.py` states that none
of its graders "asks a model to judge another model", and that stays true. This
module is the one deliberate exception, kept in its own file so the two can
never be mistaken for each other.

What it does: given two committee answers on the same frozen snapshot, both of
which have already cleared the hard gate, it asks one model which is the better
piece of analysis and why.

What that is worth, stated plainly:

  - It is an opinion. The model that prefers an answer is the same kind of
    model that wrote it, so the two share blind spots.
  - There is no outcome signal behind it. Nobody knows whether SELL was right
    on Kohl's, and this does not pretend to.
  - It decides nothing. The caller prints it for a person to read.

Two things keep the opinion from being worse than it has to be. The answers are
shown as "Answer A" and "Answer B" with nothing that says which workflow wrote
which, and which side gets which letter is drawn at random per comparison — a
model that favours whatever it reads first would otherwise favour the same side
every time. `unblind` turns the letter back into a side, and the tests hold it
to that in both orders.
"""

from __future__ import annotations

import json
import random
import re
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field

from hedge_fund.agents.guardrails import truncate_context_with_manifest
from hedge_fund.agents.llm import LLMResult, call_json, model_for_role

Side = Literal["current", "challenger"]

#: The only fields of an answer the evaluator is shown. Everything else on a
#: run — the model name, the workflow, token counts, the rebuttal record —
#: either identifies the side or is not part of the answer a reader would see.
ANSWER_FIELDS: tuple[str, ...] = (
    "stance",
    "conviction_score",
    "investment_thesis",
    "bull_case",
    "bear_case",
    "key_risks",
    "time_horizon",
    "confidence_in_data",
)

EVALUATOR_SYSTEM = """You compare two analyst answers about the same company.

Both were written from the same market data bundle, which you are given. Both
have already passed format and numeric checks, so do not re-check those.

Decide which answer is the better piece of analysis. Better means:
- its claims follow from the bundle, and it does not lean on things the bundle
  does not contain;
- its stance and conviction follow from its own reasoning;
- its risks are specific to this company rather than generic;
- where the data is thin or inconsistent, it says so.

Not grounds for preferring an answer:
- length, confidence, or polish;
- whether you would have reached the same stance. You do not know which stance
  is right, and neither does anyone else.

If the two are equally good, or differ only in wording, answer TIE. A forced
choice between equals is noise.

Refer to the answers only as "Answer A" and "Answer B".
Output valid JSON only: {"preferred": "A" | "B" | "TIE", "reason": "..."}
"""


class Preference(BaseModel):
    preferred: Literal["A", "B", "TIE"]
    reason: str = Field(default="", max_length=1200)


def assign_labels(rng: random.Random) -> dict[str, Side]:
    """Draw which side is shown as A and which as B."""
    sides: list[Side] = ["current", "challenger"]
    rng.shuffle(sides)
    return {"A": sides[0], "B": sides[1]}


def unblind(preferred: str, labels: dict[str, Side]) -> str:
    """Turn the evaluator's letter back into the side it stood for."""
    if preferred == "TIE":
        return "tie"
    return labels[preferred]


_LABEL = re.compile(r"\bAnswer ([AB])\b")


def unblind_text(text: str, labels: dict[str, Side]) -> str:
    """Rewrite "Answer A" / "Answer B" in the reason as the sides they were."""
    return _LABEL.sub(lambda m: f"[{labels[m.group(1)]}]", text)


def public_answer(analysis: dict[str, Any]) -> dict[str, Any]:
    return {k: analysis.get(k) for k in ANSWER_FIELDS}


def build_user_prompt(
    ticker: str, bundle: str, answer_a: dict[str, Any], answer_b: dict[str, Any]
) -> str:
    return f"""Ticker: {ticker}

Answer A:
{json.dumps(answer_a, ensure_ascii=False, indent=1, default=str)}

Answer B:
{json.dumps(answer_b, ensure_ascii=False, indent=1, default=str)}

The market data bundle both answers were written from (may be truncated):
{bundle}

Which answer is the better analysis? Output one JSON object:
{{"preferred": "A" | "B" | "TIE", "reason": "two or three sentences"}}
"""


Caller = Callable[..., Awaitable[LLMResult]]


async def judge(
    ticker: str,
    snapshot: dict[str, Any],
    current: dict[str, Any],
    challenger: dict[str, Any],
    *,
    rng: random.Random,
    call: Caller | None = None,
) -> dict[str, Any]:
    """One model's opinion on which of two gated answers is better.

    Returns the preference already unblinded, alongside the label assignment
    and the evaluator's raw letter, so the record shows how it was decoded.
    """
    labels = assign_labels(rng)
    by_side = {"current": public_answer(current), "challenger": public_answer(challenger)}
    bundle, _truncation = truncate_context_with_manifest(snapshot)
    user = build_user_prompt(ticker.upper(), bundle, by_side[labels["A"]], by_side[labels["B"]])

    override = model_for_role("evaluator")
    model_kwargs = {"model": override} if override else {}
    try:
        # Resolved here, not as a default argument, so a test can replace the
        # module's `call_json` and prove the evaluator was never reached.
        ask = call or call_json
        result = await ask(EVALUATOR_SYSTEM, user, Preference.model_json_schema(), **model_kwargs)
        pref = Preference.model_validate_json(result.content)
    except Exception as exc:  # noqa: BLE001
        # An evaluator that could not answer has no preference. It must not
        # read as a tie, which is an answer.
        return {"error": f"{type(exc).__name__}: {str(exc)[:200]}", "labels": labels}

    return {
        "preference": unblind(pref.preferred, labels),
        "reason": unblind_text(pref.reason, labels),
        "labels": labels,
        "raw_preferred": pref.preferred,
        "raw_reason": pref.reason,
        "model": result.model,
        "usage": result.usage,
    }
