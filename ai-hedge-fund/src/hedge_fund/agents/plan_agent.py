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
from hedge_fund.agents.llm import LLMUnavailable, OutputTruncated, call_json
from hedge_fund.agents.schemas import ResearchAnalysisOutput
from hedge_fund.agents.verifier import specs_for_facts, verify_analysis
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
from hedge_fund.plan.executor import SHARED_VALUE_CACHE
from hedge_fund.plan.registry import field_units
from hedge_fund.plan.schema import Clarification
from hedge_fund.runs import RunRecord, save_run

logger = logging.getLogger(__name__)

DEFAULT_QUESTION = "Is this an attractive investment at current levels?"

#: How many times a stage may be sent back with the harness's findings. One:
#: a second failure means the model cannot do it, and looping hides that.
MAX_REPAIRS = 1

# Each stage is constrained to the shape it must produce.
PLAN_SCHEMA = AnalysisPlan.model_json_schema()
ANALYSIS_SCHEMA = ResearchAnalysisOutput.model_json_schema()


def _llm_failure(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, OutputTruncated):
        kind = "output_truncated"
    elif isinstance(exc, LLMUnavailable):
        kind = "llm_unavailable"
    else:
        kind = "llm_error"
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


def resolve_dependency_names(plan: AnalysisPlan) -> list[dict[str, str]]:
    """Point a dependency written as a metric name at the node running it.

    Seen on the eval: `weighted_conviction` depending on "valuation_score" —
    the metric — when the node running it is called "val". The intent is
    unambiguous when exactly one node runs that metric, so the harness fixes it
    and records the fix rather than spending a model call to be told the same.

    When no node runs that metric at all, the plan named a producer it forgot
    to schedule, and the harness adds it — but only a registered metric that
    runs with no parameters, so nothing the model did not choose is guessed.
    An ambiguous or unknown name is left for the validator to reject.
    """
    from hedge_fund.plan import PlanNode, get_metric
    from hedge_fund.plan.types import MetricError

    fixes: list[dict[str, str]] = []
    ids = {n.id for n in plan.nodes}
    by_metric: dict[str, list[str]] = {}
    for n in plan.nodes:
        by_metric.setdefault(n.metric, []).append(n.id)

    for n in list(plan.nodes):
        for i, dep in enumerate(n.depends_on):
            if dep in ids:
                continue
            runs = by_metric.get(dep, [])
            if len(runs) == 1:
                n.depends_on[i] = runs[0]
                fixes.append({"node": n.id, "wrote": dep, "resolved_to": runs[0]})
                continue
            if runs:
                continue  # several nodes run it: ambiguous, the validator decides
            try:
                get_metric(dep).coerce_params({})
            except (KeyError, MetricError, ValueError):
                continue
            plan.nodes.insert(0, PlanNode(id=dep, metric=dep, why="added by the harness"))
            ids.add(dep)
            by_metric[dep] = [dep]
            fixes.append({"node": n.id, "wrote": dep, "added_step": dep})
    return fixes


def _parse_plan(
    content: str,
) -> tuple[AnalysisPlan | None, dict[str, Any] | None, list[dict[str, str]]]:
    """A validated plan and the harness's fixes to it, or the error a repair
    prompt can quote back."""
    try:
        plan = AnalysisPlan.model_validate_json(content)
        fixes = resolve_dependency_names(plan)
        validate_plan(plan)
        return plan, None, fixes
    except ValidationError as e:
        return None, {"error": "plan_schema", "message": str(e)[:800]}, []
    except PlanValidationError as e:
        return None, {"error": "plan_invalid", "message": str(e), "problems": e.problems}, []
    except Exception as e:
        return None, {"error": "plan_parse", "message": str(e)[:500]}, []


def _plan_repair_prompt(user: str, rejected: str, failure: dict[str, Any]) -> str:
    """The validator's findings, written by code, for the planner's one retry."""
    problems = failure.get("problems") or [failure.get("message", "")]
    listed = "\n".join(f"- {p}" for p in problems if p)
    return (
        f"{user}\n\nYour previous plan was rejected by the validator before anything ran:\n"
        f"{listed}\n\nThe rejected plan was:\n{rejected[:4000]}\n\n"
        "Return a corrected plan. Use only metrics and parameters from the catalog. "
        "If nothing in the catalog measures what was asked, plan the closest metrics it "
        "has and say in their `why` what it cannot measure."
    )


async def build_plan(
    ticker: str,
    question: str,
    *,
    style: str | None = None,
) -> tuple[AnalysisPlan | None, dict[str, Any]]:
    """Ask the planner for a typed plan and validate it before anything runs.

    A plan the validator rejects goes back to the planner once, with the
    validator's own list of problems. The model proposes; the harness decides
    what was wrong, so the retry is told facts rather than asked to guess.
    """
    notes = memory.retrieve(ticker=ticker)
    system = PLANNER_SYSTEM + memory.render_for_prompt(notes)
    user = build_planner_prompt(ticker, question, style)

    repair: dict[str, Any] | None = None
    for attempt in range(1 + MAX_REPAIRS):
        try:
            result = await call_json(system, user, PLAN_SCHEMA)
        except Exception as e:
            logger.exception("Planner call failed for %s", ticker)
            return None, _llm_failure(e)

        if not result.content:
            return None, {"error": "empty_response", "message": "Planner returned no content"}

        plan, failure, fixes = _parse_plan(result.content)
        if plan is not None:
            break
        assert failure is not None
        if attempt == MAX_REPAIRS:
            return None, {**failure, "repair": repair}
        repair = {
            "attempted": True,
            "first_error": failure["error"],
            "problems": failure.get("problems"),
        }
        user = _plan_repair_prompt(user, result.content, failure)

    assert plan is not None
    return plan, {
        "model": result.model,
        "params": result.params,
        "prompt_sha256": result.prompt_sha256,
        "usage": result.usage,
        "latency_ms": result.latency_ms,
        "note_ids": [n["id"] for n in notes],
        "repair": repair,
        "harness_fixes": fixes or None,
    }


async def _narrate(system: str, user: str) -> dict[str, Any]:
    """One narrator call, parsed. Errors come back as data, never raised."""
    try:
        result = await call_json(system, user, ANALYSIS_SCHEMA)
    except Exception as e:
        logger.exception("Narrator call failed")
        return _llm_failure(e)
    if not result.content:
        return {"error": "empty_response", "message": "Narrator returned no content"}
    try:
        parsed = parse_json_output(result.content)
    except GuardrailError as e:
        return {"error": "parse", "message": str(e)}
    return {"result": result, "parsed": parsed}


#: Below this the thesis is not an answer. Observed on the AAPL fixture: under
#: constrained decoding at temperature 0 the narrator returned every string
#: empty, which is valid JSON, cites nothing, and reads as a cautious HOLD.
MIN_THESIS_CHARS = 80


def _repair_trigger(
    verification: dict[str, Any], execution: dict[str, Any], analysis: dict[str, Any]
) -> str | None:
    """Why the narrative goes back, or None when it checks out."""
    if len(str(analysis.get("investment_thesis") or "").strip()) < MIN_THESIS_CHARS:
        return "empty"
    if verification["status"] == "mismatch":
        return "mismatch"
    if verification["status"] == "no_claims" and execution["ok_count"]:
        return "no_claims"
    return None


def _rank(verification: dict[str, Any], analysis: dict[str, Any]) -> tuple[bool, int, bool]:
    """Lower is better: an answer at all, then fewer wrong numbers, then citing something."""
    empty = len(str(analysis.get("investment_thesis") or "").strip()) < MIN_THESIS_CHARS
    return (empty, verification["mismatched"], verification["status"] == "no_claims")


def _verdict(verification: dict[str, Any]) -> dict[str, Any]:
    return {k: verification[k] for k in ("status", "checked", "verified", "mismatched")}


def _narrative_repair_prompt(
    user: str, previous: str, verification: dict[str, Any], trigger: str
) -> str:
    """The verifier's findings, written by code, for the narrator's one retry."""
    if trigger == "mismatch":
        wrong = [c for c in verification["claims"] if c.get("verdict") == "mismatch"]
        listed = "\n".join(
            f'- "{c.get("excerpt", "").strip()}": you wrote {c["stated"]:g}, '
            f"the computed value is {c['actual']:g}"
            for c in wrong
            if c.get("actual") is not None
        )
        finding = f"These numbers in your answer do not match the computed values:\n{listed}"
    elif trigger == "empty":
        finding = (
            "Your answer left the thesis empty. Write 3 to 6 sentences that answer the "
            "question from the computed values above, quoting each value you rely on "
            "and naming any value that is missing."
        )
    else:
        finding = (
            "Your answer cites none of the computed values, so no conclusion in it "
            "can be traced to the analysis. Support each claim with the value from "
            "the facts above, written as it appears there."
        )
    return (
        f"{user}\n\nYour previous answer was checked by code before anyone read it.\n"
        f"{finding}\n\nYour previous answer was:\n{previous[:6000]}\n\n"
        "Return the full answer again with these corrected. Change nothing else."
    )


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
    # Widened so the early return below is what narrows it: a planner failure
    # returns metadata in place of a plan, and executing `None` would be the
    # one way this pipeline could emit numbers nothing chose.
    plan: AnalysisPlan | None
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
        execution = execute_plan(
            plan,
            ticker,
            data_snapshot,
            data_service=data_service,
            value_cache=SHARED_VALUE_CACHE,
        )
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
    # Claims are checked against the computed facts as well as the raw snapshot,
    # since the narrator was told to cite the former.
    checked_against = {**data_snapshot, "computed": execution["facts"]}
    fact_specs = specs_for_facts(
        execution["facts"],
        [n.get("values") or {} for n in execution["nodes"] if n["status"] == "ok"],
        field_units(),
    )

    narrated = await _narrate(system, user)
    if "error" in narrated:
        return {**narrated, "plan": plan.as_dict(), "execution": execution}
    result, parsed = narrated["result"], narrated["parsed"]
    verification = verify_analysis(parsed.model_dump(), checked_against, fact_specs)

    # --- 3b. repair ----------------------------------------------------
    # The verifier is the validator and this block is the debugger: code
    # writes the correction, the model only rewrites. One retry, and the
    # better-checked version wins, so a repair can never make a run worse.
    repair: dict[str, Any] | None = None
    trigger = _repair_trigger(verification, execution, parsed.model_dump())
    if trigger:
        repair = {"attempted": True, "trigger": trigger, "before": _verdict(verification)}
        retry = await _narrate(
            system, _narrative_repair_prompt(user, result.content, verification, trigger)
        )
        if "error" in retry:
            repair.update(kept="original", error=retry["error"])
        else:
            second = verify_analysis(retry["parsed"].model_dump(), checked_against, fact_specs)
            repair["after"] = _verdict(second)
            repair["usage"] = retry["result"].usage
            if _rank(second, retry["parsed"].model_dump()) < _rank(
                verification, parsed.model_dump()
            ):
                result, parsed, verification = retry["result"], retry["parsed"], second
                repair["kept"] = "repaired"
            else:
                repair["kept"] = "original"

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

    if repair is not None:
        evaluation["repair"] = repair
        evaluation.setdefault("notes", []).append(
            f"narrative sent back once ({repair['trigger'].replace('_', ' ')}); "
            f"kept the {repair['kept']} version"
        )
    if plan_meta.get("repair"):
        evaluation["plan_repair"] = plan_meta["repair"]
    if plan_meta.get("harness_fixes"):
        evaluation["plan_fixes"] = plan_meta["harness_fixes"]
        evaluation.setdefault("notes", []).append(
            f"the harness pointed {len(plan_meta['harness_fixes'])} dependency name(s) "
            "at the step that computes them"
        )
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
        "usage": {
            "planner": plan_meta.get("usage"),
            "narrator": result.usage,
            "narrator_repair": (repair or {}).get("usage"),
        },
        "repair": repair,
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
