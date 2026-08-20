"""Plan-based research: compile the question, compute the numbers, then write.

This is the alternative to handing a model a data dump and asking for a verdict.
The pipeline is plan → execute → narrate, and the model appears twice, in two
narrow roles that are separated on purpose:

1. **Planner** — picks metrics from a fixed catalog. Sees no values, so it cannot
   reason from a number it made up.
2. **Executor** — ordinary Python. Produces every figure the answer rests on.
3. **Narrator** — sees only computed values and is instructed to do no arithmetic.

The harness has the last word. When the plan computed a conviction score, that
value replaces whatever the narrator wrote, and the substitution is recorded. A
number in the output is then traceable to the node that produced it rather than
to a sampling decision.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import ValidationError

from hedge_fund.agents import memory
from hedge_fund.agents.evaluation import evaluate_research
from hedge_fund.agents.guardrails import (
    GuardrailError,
    parse_json_output,
    sanitize_ticker,
    validate_output,
)
from hedge_fund.agents.llm import LLMUnavailable, call_json
from hedge_fund.agents.verifier import verify_analysis
from hedge_fund.plan import (
    AnalysisPlan,
    PlanValidationError,
    execute_plan,
    render_facts_for_prompt,
    validate_plan,
)
from hedge_fund.plan.prompts import (
    NARRATOR_SYSTEM,
    PLANNER_SYSTEM,
    build_narrator_prompt,
    build_planner_prompt,
)
from hedge_fund.plan.schema import Clarification
from hedge_fund.runs import RunRecord, save_run

logger = logging.getLogger(__name__)

DEFAULT_QUESTION = "Is this an attractive investment at current levels?"


def _llm_failure(exc: Exception) -> dict[str, Any]:
    kind = "llm_unavailable" if isinstance(exc, LLMUnavailable) else "llm_error"
    return {"error": kind, "message": str(exc)}


def _apply_answers(plan: AnalysisPlan, answers: dict[str, str] | None) -> list[str]:
    """Record the user's methodology choices on the plan. Returns unknown ids."""
    if not answers:
        return []
    by_id = {c.id: c for c in plan.clarifications}
    unknown = [k for k in answers if k not in by_id]
    for cid, answer in answers.items():
        if cid in by_id:
            by_id[cid].answer = answer
    return unknown


async def build_plan(
    ticker: str,
    question: str,
    *,
    style: str | None = None,
) -> tuple[AnalysisPlan | None, dict[str, Any]]:
    """Ask the planner for a typed plan and validate it before anything runs."""
    notes = memory.retrieve(ticker=ticker)
    system = PLANNER_SYSTEM + memory.render_for_prompt(notes)
    user = build_planner_prompt(ticker, question, style)

    try:
        result = await call_json(system, user)
    except Exception as e:
        logger.exception("Planner call failed for %s", ticker)
        return None, _llm_failure(e)

    if not result.content:
        return None, {"error": "empty_response", "message": "Planner returned no content"}

    try:
        plan = AnalysisPlan.model_validate_json(result.content)
        validate_plan(plan)
    except ValidationError as e:
        return None, {"error": "plan_schema", "message": str(e)[:800]}
    except PlanValidationError as e:
        return None, {"error": "plan_invalid", "message": str(e), "problems": e.problems}
    except Exception as e:
        return None, {"error": "plan_parse", "message": str(e)[:500]}

    return plan, {
        "model": result.model,
        "params": result.params,
        "prompt_sha256": result.prompt_sha256,
        "usage": result.usage,
        "latency_ms": result.latency_ms,
        "note_ids": [n["id"] for n in notes],
    }


async def run_plan_analysis(
    ticker: str,
    data_snapshot: dict[str, Any],
    *,
    question: str = "",
    style: str | None = None,
    data_service: Any = None,
    clarification_answers: dict[str, str] | None = None,
    plan_override: dict[str, Any] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Full plan → execute → narrate pipeline for one ticker.

    Pass ``plan_override`` to re-run an edited plan without re-planning; combined
    with the executor's value cache this is what makes iterating on a plan cheap.
    """
    try:
        sanitize_ticker(ticker)
    except GuardrailError as e:
        return {"error": "guardrail", "message": str(e)}

    question = question.strip() or DEFAULT_QUESTION
    started = time.perf_counter()

    # --- 1. plan -------------------------------------------------------
    if plan_override is not None:
        try:
            plan = validate_plan(AnalysisPlan.model_validate(plan_override))
        except ValidationError as e:
            return {"error": "plan_schema", "message": str(e)[:800]}
        except PlanValidationError as e:
            return {"error": "plan_invalid", "message": str(e), "problems": e.problems}
        plan_meta: dict[str, Any] = {"source": "override"}
    else:
        plan, plan_meta = await build_plan(ticker, question, style=style)
        if plan is None:
            return plan_meta

    unknown = _apply_answers(plan, clarification_answers)

    # --- 2. execute ----------------------------------------------------
    try:
        execution = execute_plan(plan, ticker, data_snapshot, data_service=data_service)
    except PlanValidationError as e:
        return {"error": "plan_invalid", "message": str(e), "problems": e.problems}

    pending = [c.as_dict() for c in plan.clarifications if c.answer is None]

    if execution["ok_count"] == 0:
        return {
            "error": "plan_execution_failed",
            "message": "No node in the plan produced a value",
            "plan": plan.as_dict(),
            "execution": execution,
        }

    # --- 3. narrate ----------------------------------------------------
    facts_block = render_facts_for_prompt(execution)
    notes = memory.retrieve(ticker=ticker)
    system = NARRATOR_SYSTEM + memory.render_for_prompt(notes)
    user = build_narrator_prompt(ticker.upper(), question, facts_block, data_snapshot)

    try:
        result = await call_json(system, user)
    except Exception as e:
        logger.exception("Narrator call failed for %s", ticker)
        return {**_llm_failure(e), "plan": plan.as_dict(), "execution": execution}

    if not result.content:
        return {
            "error": "empty_response",
            "message": "Narrator returned no content",
            "plan": plan.as_dict(),
            "execution": execution,
        }

    try:
        parsed = parse_json_output(result.content)
    except GuardrailError as e:
        return {
            "error": "parse",
            "message": str(e),
            "plan": plan.as_dict(),
            "execution": execution,
        }

    analysis = parsed.model_dump()

    # --- 4. the harness decides ---------------------------------------
    overrides: list[dict[str, Any]] = []
    computed_conviction = execution["facts"].get("conviction_score")
    if isinstance(computed_conviction, (int, float)):
        stated = analysis.get("conviction_score")
        if stated != int(computed_conviction):
            overrides.append(
                {
                    "field": "conviction_score",
                    "model_said": stated,
                    "harness_used": int(computed_conviction),
                    "source": "weighted_conviction node",
                }
            )
        analysis["conviction_score"] = int(computed_conviction)

    evaluation = evaluate_research(parsed, data_snapshot=data_snapshot)
    evaluation["guardrail_warnings"] = validate_output(parsed)

    # Claims are checked against the computed facts as well as the raw snapshot,
    # since the narrator was told to cite the former.
    verification = verify_analysis(analysis, {**data_snapshot, "computed": execution["facts"]})
    if verification["status"] == "mismatch":
        evaluation.setdefault("notes", []).append(
            f"{verification['mismatched']} numeric claim(s) contradict the snapshot"
        )
    if overrides:
        evaluation.setdefault("notes", []).append(
            "conviction_score was replaced with the value computed by the plan"
        )
    # A thesis that cites none of the computed values is not grounded in them,
    # however confident it sounds. "No claims" must not read as "checks passed".
    if execution["ok_count"] and verification["status"] == "no_claims":
        evaluation.setdefault("notes", []).append(
            f"narrative cites none of the {execution['ok_count']} computed values — "
            "conclusions are not traceable to the plan"
        )
        evaluation["narrative_grounded"] = False
    else:
        evaluation["narrative_grounded"] = verification["status"] != "mismatch"
    if execution["error_count"]:
        evaluation.setdefault("notes", []).append(
            f"{execution['error_count']} plan node(s) failed to compute"
        )

    out: dict[str, Any] = {
        "analysis": analysis,
        "evaluation": evaluation,
        "verification": verification,
        "plan": plan.as_dict(),
        "execution": execution,
        "clarifications_pending": pending,
        "harness_overrides": overrides,
        "model": result.model,
        "planner_model": plan_meta.get("model"),
        "model_params": result.params,
        "prompt_sha256": result.prompt_sha256,
        "fingerprint": result.fingerprint,
        "usage": {"planner": plan_meta.get("usage"), "narrator": result.usage},
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "methodology_note_ids": [n["id"] for n in notes],
    }
    if unknown:
        out["unknown_clarification_ids"] = unknown

    if persist:
        out["run_uid"] = save_run(
            RunRecord(
                ticker=ticker.upper(),
                mode="plan",
                snapshot=data_snapshot,
                model=result.model,
                model_params=result.params,
                prompt_sha256=result.prompt_sha256,
                fingerprint=result.fingerprint,
                output=analysis,
                evaluation=evaluation,
                verification=verification,
                plan={
                    "plan": plan.as_dict(),
                    "plan_hash": execution["plan_hash"],
                    "facts": execution["facts"],
                    "nodes": execution["nodes"],
                    "overrides": overrides,
                },
                usage=out["usage"],
                latency_ms=out["latency_ms"],
                methodology_note_ids=out["methodology_note_ids"],
            )
        )
    return out


def describe_clarifications(plan: AnalysisPlan) -> list[dict[str, Any]]:
    """The plan's open methodology questions, for a UI to render."""
    return [c.as_dict() for c in plan.clarifications]


__all__ = [
    "Clarification",
    "DEFAULT_QUESTION",
    "build_plan",
    "describe_clarifications",
    "run_plan_analysis",
]
