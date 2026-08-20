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
from hedge_fund.agents.llm import LLMResult, LLMUnavailable, call_json
from hedge_fund.agents.personas import (
    SYNTHESIS_SYSTEM,
    build_pm_synthesis_user_prompt,
    get_persona_system_prompt,
)
from hedge_fund.agents.prompts import RESEARCH_SYSTEM, build_user_prompt
from hedge_fund.agents.verifier import verify_analysis
from hedge_fund.runs import RunRecord, save_run

logger = logging.getLogger(__name__)


def _llm_failure(exc: Exception) -> dict[str, Any]:
    kind = "llm_unavailable" if isinstance(exc, LLMUnavailable) else "llm_error"
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
) -> dict[str, Any]:
    """One analysis call: prompt assembly, invocation, parsing, checking."""
    system, notes = _assemble_system_prompt(system_base, ticker=ticker, persona_id=persona_id)
    bundle, truncation = truncate_context_with_manifest(snapshot)
    user_msg = build_user_prompt(ticker.upper(), bundle)

    try:
        result = await call_json(system, user_msg)
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

    out = await _analyze(ticker, data_snapshot, system_base=system_base, persona_id=persona_id)

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
        result = await call_json(system, user_msg)
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

    synth_input = [
        {"persona_id": c["persona_id"], "analysis": c.get("analysis")} for c in successes
    ]
    synth = await run_pm_synthesis(ticker, data_snapshot, synth_input)

    out: dict[str, Any] = {
        "committee": committee,
        "synthesis": synth,
        "dissent": summarize_dissent(committee),
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
            committee_detail=committee,
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
