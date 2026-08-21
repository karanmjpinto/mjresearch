"""Research synthesis — Ollama (default, local/free) or optional OpenAI.

Each analysis is a recorded run: an immutable snapshot in, a schema-validated
output out, plus the deterministic checks that ran over it (heuristic evaluation,
guardrail warnings, and numeric claim verification against the snapshot). The
run is persisted so it can be replayed, diffed, and regression-tested — the model
proposes, and the surrounding harness decides what is trustworthy.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from hedge_fund.agents import memory
from hedge_fund.agents.evaluation import evaluate_research
from hedge_fund.agents.guardrails import (
    GuardrailError,
    parse_json_output,
    sanitize_ticker,
    truncate_context_with_manifest,
    validate_output,
)
from hedge_fund.agents.llm import (
    LLMResult,
    LLMUnavailable,
    OutputTruncated,
    call_json,
    model_for_role,
)
from hedge_fund.agents.personas import (
    SYNTHESIS_SYSTEM,
    build_pm_synthesis_user_prompt,
    build_rebuttal_user_prompt,
    get_persona_system_prompt,
    get_rebuttal_system_prompt,
)
from hedge_fund.agents.prompts import RESEARCH_SYSTEM, build_user_prompt
from hedge_fund.agents.schemas import ResearchAnalysisOutput
from hedge_fund.agents.verifier import verify_analysis
from hedge_fund.runs import RunRecord, save_run
from hedge_fund.settings import settings

logger = logging.getLogger(__name__)

# Constrains generation to the analysis shape, not merely to valid JSON.
ANALYSIS_SCHEMA = ResearchAnalysisOutput.model_json_schema()


def _model_kwargs(role: str) -> dict[str, Any]:
    """Model override for a stage, omitted entirely when none is configured.

    Absent rather than ``model=None`` on purpose: with no override configured the
    call is identical to the one this code made before per-stage selection
    existed, so the default path cannot regress.
    """
    override = model_for_role(role)
    return {"model": override} if override else {}


def _llm_failure(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, OutputTruncated):
        kind = "output_truncated"
    elif isinstance(exc, LLMUnavailable):
        kind = "llm_unavailable"
    else:
        kind = "llm_error"
    return {"error": kind, "message": str(exc)}


def _assemble_system_prompt(
    base: str, *, ticker: str, persona_id: str | None
) -> tuple[str, list[dict[str, Any]]]:
    """Base prompt plus any methodology notes that apply to this run."""
    notes = memory.retrieve(ticker=ticker, persona=persona_id)
    section = memory.render_for_prompt(notes)
    return (base + section if section else base), notes


def _finalize(
    parsed: Any,
    snapshot: dict[str, Any],
    result: LLMResult,
) -> dict[str, Any]:
    """Run every deterministic check over a parsed model output."""
    analysis = parsed.model_dump()
    evaluation = evaluate_research(parsed, data_snapshot=snapshot)
    evaluation["guardrail_warnings"] = validate_output(parsed)
    verification = verify_analysis(analysis, snapshot)
    if verification["status"] == "mismatch":
        evaluation.setdefault("notes", []).append(
            f"{verification['mismatched']} numeric claim(s) contradict the snapshot"
        )
    return {
        "analysis": analysis,
        "evaluation": evaluation,
        "verification": verification,
        "model": result.model,
        "usage": result.usage,
        "model_params": result.params,
        "prompt_sha256": result.prompt_sha256,
        "fingerprint": result.fingerprint,
        "latency_ms": result.latency_ms,
    }


async def _analyze(
    ticker: str,
    snapshot: dict[str, Any],
    *,
    system_base: str,
    persona_id: str | None,
    role: str = "single",
) -> dict[str, Any]:
    """One analysis call: prompt assembly, invocation, parsing, checking."""
    system, notes = _assemble_system_prompt(system_base, ticker=ticker, persona_id=persona_id)
    bundle, truncation = truncate_context_with_manifest(snapshot)
    user_msg = build_user_prompt(ticker.upper(), bundle)

    try:
        result = await call_json(system, user_msg, ANALYSIS_SCHEMA, **_model_kwargs(role))
    except Exception as e:
        logger.exception("LLM call failed for %s", ticker)
        return _llm_failure(e)

    if not result.content:
        return {"error": "empty_response", "message": "Model returned no content"}

    try:
        parsed = parse_json_output(result.content)
    except GuardrailError as e:
        return {"error": "parse", "message": str(e)}

    out = _finalize(parsed, snapshot, result)
    out["methodology_note_ids"] = [n["id"] for n in notes]
    if truncation.get("truncated"):
        out["evaluation"].setdefault("notes", []).append(
            "context was reduced to fit the model limit — see context_truncation"
        )
        out["context_truncation"] = truncation
    return out


async def run_research_analysis(
    ticker: str,
    data_snapshot: dict[str, Any],
    *,
    persona_id: str | None = None,
    persist: bool = True,
    role: str | None = None,
) -> dict[str, Any]:
    """Returns structured analysis + evaluation metadata, or error dict.

    If persona_id is set, use that investor-style system prompt (see agents.personas).
    """
    try:
        sanitize_ticker(ticker)
    except GuardrailError as e:
        return {"error": "guardrail", "message": str(e)}

    system_base = RESEARCH_SYSTEM
    if persona_id:
        try:
            system_base = get_persona_system_prompt(persona_id)
        except ValueError as e:
            return {"error": "invalid_persona", "message": str(e)}

    out = await _analyze(
        ticker,
        data_snapshot,
        system_base=system_base,
        persona_id=persona_id,
        role=role or ("persona" if persona_id else "single"),
    )

    if persona_id and "error" not in out:
        out["persona_id"] = persona_id.strip().lower()

    if persist:
        out["run_uid"] = save_run(
            RunRecord(
                ticker=ticker.upper(),
                mode="persona" if persona_id else "single",
                snapshot=data_snapshot,
                persona_id=persona_id,
                model=out.get("model"),
                model_params=out.get("model_params"),
                prompt_sha256=out.get("prompt_sha256"),
                fingerprint=out.get("fingerprint"),
                output=out.get("analysis"),
                evaluation=out.get("evaluation"),
                verification=out.get("verification"),
                usage=out.get("usage"),
                latency_ms=out.get("latency_ms"),
                error={k: out[k] for k in ("error", "message") if k in out} or None,
                methodology_note_ids=out.get("methodology_note_ids"),
            )
        )
    return out


async def run_pm_synthesis(
    ticker: str,
    data_snapshot: dict[str, Any],
    persona_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Combine persona analyses into one ResearchAnalysisOutput-shaped result."""
    system, notes = _assemble_system_prompt(SYNTHESIS_SYSTEM, ticker=ticker, persona_id=None)
    bundle, _truncation = truncate_context_with_manifest(data_snapshot)
    persona_json = json.dumps(persona_results, ensure_ascii=False, default=str)
    user_msg = build_pm_synthesis_user_prompt(ticker.upper(), persona_json) + (
        f"\n\nOriginal market data bundle (may be truncated):\n{bundle}"
    )

    try:
        result = await call_json(system, user_msg, ANALYSIS_SCHEMA, **_model_kwargs("synthesis"))
    except Exception as e:
        logger.exception("LLM synthesis failed for %s", ticker)
        return _llm_failure(e)

    if not result.content:
        return {"error": "empty_response", "message": "Model returned no content"}

    try:
        parsed = parse_json_output(result.content)
    except GuardrailError as e:
        return {"error": "parse", "message": str(e)}

    out = _finalize(parsed, data_snapshot, result)
    out["methodology_note_ids"] = [n["id"] for n in notes]
    return out


def _peer_summary(committee: list[dict[str, Any]], exclude_persona: str) -> str:
    """The other analysts' conclusions, anonymized and compact.

    Anonymized because the point of the round is to test arguments; a label like
    "Warren Buffett" carries authority that the argument may not, and a model is
    quite willing to defer to the name. Compact because the bundle still has to
    fit alongside it in the context window.
    """
    lines: list[str] = []
    label = ord("A")
    for entry in committee:
        analysis = entry.get("analysis")
        if entry.get("persona_id") == exclude_persona or not isinstance(analysis, dict):
            continue
        thesis = str(analysis.get("investment_thesis") or "")[:600]
        lines.append(
            f"Analyst {chr(label)} — stance {analysis.get('stance')}, "
            f"conviction {analysis.get('conviction_score')}\n"
            f"  thesis: {thesis}\n"
            f"  bear case: {str(analysis.get('bear_case') or '')[:300]}"
        )
        label += 1
    return "\n".join(lines) if lines else "(no other analyst produced a view)"


def _describe_contention(dissent: dict[str, Any]) -> str:
    """One line naming what the committee actually split over."""
    stances = dissent.get("stances") or {}
    stance_str = ", ".join(f"{k}x{v}" for k, v in sorted(stances.items()))
    return (
        f"conviction ranged {dissent.get('conviction_min')}-{dissent.get('conviction_max')} "
        f"across {dissent.get('responded')} analysts (spread "
        f"{dissent.get('conviction_spread')}); stances: {stance_str or 'n/a'}"
    )


async def _rebut_one(
    ticker: str,
    snapshot: dict[str, Any],
    *,
    persona_id: str,
    own_analysis: dict[str, Any],
    peer_views: str,
    contention: str,
) -> dict[str, Any]:
    """One persona's second look. Same snapshot, plus what the others concluded."""
    system, notes = _assemble_system_prompt(
        get_rebuttal_system_prompt(persona_id), ticker=ticker, persona_id=persona_id
    )
    bundle, _truncation = truncate_context_with_manifest(snapshot)
    own = json.dumps(own_analysis, ensure_ascii=False, default=str)
    user_msg = build_rebuttal_user_prompt(ticker.upper(), bundle, own, peer_views, contention)

    try:
        result = await call_json(system, user_msg, ANALYSIS_SCHEMA, **_model_kwargs("persona"))
    except Exception as e:
        logger.exception("Rebuttal call failed for %s/%s", ticker, persona_id)
        return _llm_failure(e)
    if not result.content:
        return {"error": "empty_response", "message": "Model returned no content"}
    try:
        parsed = parse_json_output(result.content)
    except GuardrailError as e:
        return {"error": "parse", "message": str(e)}

    # Revised output is verified against the snapshot exactly as the first round
    # was. A second opinion gets no exemption from the numeric checks.
    out = _finalize(parsed, snapshot, result)
    out["methodology_note_ids"] = [n["id"] for n in notes]
    return out


async def _run_rebuttal_round(
    ticker: str,
    snapshot: dict[str, Any],
    committee: list[dict[str, Any]],
    dissent: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Re-run every persona that produced a view, showing it the others'.

    Returns (merged_committee, round2_entries). A persona whose second call fails
    keeps its first-round view: a failed rebuttal must not delete an opinion the
    committee already legitimately held.
    """
    contention = _describe_contention(dissent)
    respondents = [c for c in committee if isinstance(c.get("analysis"), dict)]

    tasks = [
        _rebut_one(
            ticker,
            snapshot,
            persona_id=c["persona_id"],
            own_analysis=c["analysis"],
            peer_views=_peer_summary(committee, c["persona_id"]),
            contention=contention,
        )
        for c in respondents
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    revised_by_persona: dict[str, dict[str, Any]] = {}
    round2: list[dict[str, Any]] = []
    for entry, one in zip(respondents, results):
        pid = entry["persona_id"]
        if isinstance(one, BaseException):
            round2.append(
                {
                    "persona_id": pid,
                    "round": 2,
                    "error": {"error": "persona_exception", "message": str(one)},
                }
            )
            continue
        if "error" in one:
            round2.append({"persona_id": pid, "round": 2, "error": one})
            continue

        before, after = entry["analysis"], one["analysis"]
        record = {
            "persona_id": pid,
            "round": 2,
            "analysis": after,
            "evaluation": one.get("evaluation"),
            "verification": one.get("verification"),
            "model": one.get("model"),
            "usage": one.get("usage"),
            "conviction_before": before.get("conviction_score"),
            "conviction_after": after.get("conviction_score"),
            "stance_before": before.get("stance"),
            "stance_after": after.get("stance"),
            "revised": (
                before.get("conviction_score") != after.get("conviction_score")
                or before.get("stance") != after.get("stance")
            ),
        }
        round2.append(record)
        revised_by_persona[pid] = record

    merged = [
        {**revised_by_persona[c["persona_id"]]} if c.get("persona_id") in revised_by_persona else c
        for c in committee
    ]
    return merged, round2


async def run_committee_analysis(
    ticker: str,
    data_snapshot: dict[str, Any],
    persona_ids: list[str],
) -> dict[str, Any]:
    """Run personas concurrently against one frozen snapshot, then synthesize.

    Every persona reads the same immutable snapshot, so a disagreement between
    them is a difference of judgement rather than a difference of data — which it
    would silently become if each re-fetched and a cache expired mid-fan-out.
    """
    if not persona_ids:
        return {"error": "invalid_committee", "message": "committee_personas is empty"}

    started = time.perf_counter()

    # Fan-out: all persona analyses in flight simultaneously. Individual runs are
    # not persisted here; the committee is recorded once, as a whole.
    persona_tasks = [
        run_research_analysis(ticker, data_snapshot, persona_id=pid, persist=False)
        for pid in persona_ids
    ]
    persona_results = await asyncio.gather(*persona_tasks, return_exceptions=True)

    committee: list[dict[str, Any]] = []
    usages: list[dict[str, Any]] = []
    for pid, one in zip(persona_ids, persona_results):
        if isinstance(one, BaseException):
            committee.append(
                {
                    "persona_id": pid,
                    "error": {"error": "persona_exception", "message": str(one)},
                }
            )
            continue
        if "error" in one:
            committee.append({"persona_id": pid, "error": one})
        else:
            committee.append(
                {
                    "persona_id": pid,
                    "analysis": one.get("analysis"),
                    "evaluation": one.get("evaluation"),
                    "verification": one.get("verification"),
                    "model": one.get("model"),
                    "usage": one.get("usage"),
                }
            )
            if one.get("usage"):
                usages.append(one["usage"])

    successes = [c for c in committee if "analysis" in c]
    if not successes:
        return {
            "error": "committee_failed",
            "message": "All persona runs failed",
            "committee": committee,
        }

    # The committee has spoken once. If it split materially, the synthesis would
    # otherwise average away a disagreement nobody has examined — so put the
    # analysts back in the room first and let the split either resolve or harden.
    # Only the verdict of the *second* round reaches the PM.
    first_round = [{**c, "round": 1} for c in committee]
    dissent_first = summarize_dissent(committee)
    refinement: dict[str, Any] = {
        "triggered": False,
        "enabled": bool(settings.committee_refine_on_dissent),
        "reason": None,
    }
    round2: list[dict[str, Any]] = []

    if settings.committee_refine_on_dissent and dissent_first.get("material_disagreement"):
        refinement["reason"] = _describe_contention(dissent_first)
        refinement["triggered"] = True
        committee, round2 = await _run_rebuttal_round(
            ticker, data_snapshot, committee, dissent_first
        )
        successes = [c for c in committee if isinstance(c.get("analysis"), dict)]
        usages.extend(c["usage"] for c in round2 if c.get("usage"))

    dissent_final = summarize_dissent(committee)
    if refinement["triggered"]:
        revised = [c["persona_id"] for c in round2 if c.get("revised")]
        spread_before = dissent_first.get("conviction_spread")
        spread_after = dissent_final.get("conviction_spread")
        refinement.update(
            {
                "revised_personas": revised,
                "held_personas": [
                    c["persona_id"] for c in round2 if "analysis" in c and not c.get("revised")
                ],
                "failed_personas": [c["persona_id"] for c in round2 if "error" in c],
                "conviction_spread_before": spread_before,
                "conviction_spread_after": spread_after,
                "resolved": not dissent_final.get("material_disagreement"),
            }
        )
        # Total convergence after one round is the signature of deference, not
        # of agreement — flag it rather than letting the PM read unanimity as
        # independent confirmation.
        if (
            dissent_final.get("unanimous_stance")
            and spread_after == 0
            and len(revised) >= max(2, len(round2) - 1)
        ):
            refinement["suspect_convergence"] = True
            refinement["note"] = (
                "every dissenting analyst moved to the same view in one round; "
                "treat this as deference to the group rather than independent agreement"
            )

    synth_input = [
        {"persona_id": c["persona_id"], "analysis": c.get("analysis")} for c in successes
    ]
    synth = await run_pm_synthesis(ticker, data_snapshot, synth_input)

    out: dict[str, Any] = {
        "committee": committee,
        "committee_round1": first_round if refinement["triggered"] else None,
        "synthesis": synth,
        "dissent": dissent_final,
        "dissent_round1": dissent_first if refinement["triggered"] else None,
        "refinement": refinement,
    }
    if "error" not in synth and synth.get("usage"):
        usages.append(synth["usage"])
    out["usage_total"] = usages

    out["run_uid"] = save_run(
        RunRecord(
            ticker=ticker.upper(),
            mode="committee",
            snapshot=data_snapshot,
            committee_personas=list(persona_ids),
            model=synth.get("model"),
            model_params=synth.get("model_params"),
            prompt_sha256=synth.get("prompt_sha256"),
            fingerprint=synth.get("fingerprint"),
            output=synth.get("analysis"),
            evaluation=synth.get("evaluation"),
            verification=synth.get("verification"),
            committee_detail=first_round + round2,
            usage={"per_persona": usages},
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=None if "error" not in synth else synth,
            methodology_note_ids=synth.get("methodology_note_ids"),
        )
    )
    return out


def summarize_dissent(committee: list[dict[str, Any]]) -> dict[str, Any]:
    """Quantify committee disagreement instead of leaving it inside the prose.

    A synthesis that reconciles a 40-point conviction spread deserves to be read
    differently from one where every persona already agreed, and that distinction
    is lost once it has been flattened into a single number.
    """
    scores: list[int] = []
    stances: dict[str, int] = {}
    for entry in committee:
        analysis = entry.get("analysis")
        if not isinstance(analysis, dict):
            continue
        score = analysis.get("conviction_score")
        if isinstance(score, (int, float)):
            scores.append(int(score))
        stance = analysis.get("stance")
        if isinstance(stance, str):
            stances[stance] = stances.get(stance, 0) + 1

    if not scores:
        return {"responded": 0}

    spread = max(scores) - min(scores)
    return {
        "responded": len(scores),
        "conviction_min": min(scores),
        "conviction_max": max(scores),
        "conviction_mean": round(sum(scores) / len(scores), 1),
        "conviction_spread": spread,
        "stances": stances,
        "unanimous_stance": len(stances) == 1,
        # A spread this wide means the personas are not analysing the same
        # question; the synthesis is averaging away a real disagreement.
        "material_disagreement": spread >= 30 or len(stances) > 2,
    }
