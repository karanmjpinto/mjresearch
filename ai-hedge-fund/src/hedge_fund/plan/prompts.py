"""Prompts for the two model calls in a plan-based analysis.

The split is the point. The planner chooses *what to measure* and never sees a
number; the narrator sees only numbers the harness computed and is forbidden from
producing new ones. Neither call is in a position to invent a figure and then
reason from it.
"""

from __future__ import annotations

from typing import Any

from hedge_fund.plan.registry import catalog


def render_catalog() -> str:
    """The metric catalog as the planner sees it."""
    lines: list[str] = []
    for spec in catalog():
        lines.append(f"\n{spec['metric']} [{spec['tier']}] — {spec['label']}")
        lines.append(f"  {spec['description']}")
        if spec["params"]:
            lines.append("  params:")
            for p in spec["params"]:
                bits = [f"type={p['type']}"]
                if "default" in p:
                    bits.append(f"default={p['default']}")
                if "minimum" in p or "maximum" in p:
                    bits.append(f"range={p.get('minimum', '-')}..{p.get('maximum', '-')}")
                lines.append(f"    - {p['name']} ({', '.join(bits)}): {p['description']}")
        outs = ", ".join(f["name"] for f in spec["outputs"])
        lines.append(f"  outputs: {outs}")
        if spec.get("consumes"):
            lines.append(f"  reads outputs of: {', '.join(spec['consumes'])}")
        if spec.get("notes"):
            lines.append(f"  note: {spec['notes']}")
    return "\n".join(lines)


PLANNER_SYSTEM = """You are the planning stage of a buy-side research system.

You do NOT analyse the company and you do NOT produce any numbers. You choose
which deterministic metrics should be computed to answer the question, and the
system computes them. Anything you assert about values would be discarded.

Rules:
- Use ONLY metric ids from the catalog. Never invent a metric or a parameter.
- Most questions need no formula. Only if no metric measures what the
  question asks, write a `formula` step over
  the statement series and the values other steps compute — for example
  pct(abs(latest(dividends)), latest(free_cash_flow)) for the share of free
  cash flow paid as dividends. Prefer a metric whenever one fits. A formula
  that uses another step's value must depend on that step.
- If neither a metric nor a formula can measure it, do not invent a metric.
  Plan the closest metrics and say in their `why` what cannot be measured.
- Give every node a short, unique id and a one-line `why`.
- Set `depends_on` for any node that reads another node's outputs (see "reads
  outputs of" in the catalog). Order otherwise does not matter.
- Prefer 5-9 nodes. Cover valuation, trend/momentum, risk, and — when the
  question is about attractiveness or a decision — finish with
  weighted_conviction so the conclusion is reproducible from the plan.
- Choose weights that reflect the stated investing style. Justify them in `why`.
- If a genuine methodology choice would change the result, add a clarification:
  a closed-form question, 2-4 concrete options, and a RECOMMENDED default. Only
  raise choices a good analyst would actually put to a portfolio manager. Never
  ask the user for data, and never ask more than two questions.
- Output valid JSON only. No markdown fences.
"""


def build_planner_prompt(ticker: str, question: str, style: str | None = None) -> str:
    style_line = (
        f"\nInvesting style to reflect in metric choice and weights: {style}\n" if style else ""
    )
    return f"""Ticker: {ticker}
Question: {question or f"Is {ticker} an attractive investment at current levels?"}
{style_line}
Available metrics:
{render_catalog()}

Return a single JSON object:
{{
  "question": "restate the question you are planning for",
  "nodes": [
    {{"id": "short_id", "metric": "metric_id", "params": {{}}, "depends_on": [], "why": "one line"}}
  ],
  "clarifications": [
    {{"id": "short_id", "question": "...", "options": ["a", "b"], "recommended": "a", "affects": ["node_id"]}}
  ]
}}
"""


NARRATOR_SYSTEM = """You are the writing stage of a buy-side research system.

Every number you may use has already been computed and is given to you below.

Absolute rules:
- Use ONLY the computed values provided. Do NOT calculate, estimate, adjust,
  annualise, or infer any new figure — not even simple arithmetic.
- Quote values exactly as given, with the same units.
- If something needed to answer the question was NOT computed or is marked NOT
  AVAILABLE, say so plainly and lower confidence_in_data. Do not fill the gap.
- If a conviction_score was computed, use that exact value. Do not adjust it.
- Output valid JSON matching the schema exactly. No markdown fences.
- stance must be one of: BUY, HOLD, SELL, WATCH.
- Keep key_risks to specific, material risks grounded in the computed values.
- Write for a person, not a program: "book value per share rose 57.04% over
  three years", never "bvps_change_3y_pct=57.04". Field names stay out of the
  prose; the values and their units go in.
"""


def build_narrator_prompt(
    ticker: str,
    question: str,
    facts_block: str,
    context: dict[str, Any] | None = None,
) -> str:
    ctx_line = ""
    if context:
        fundamentals = context.get("fundamentals") or {}
        sector = fundamentals.get("sector")
        currency = fundamentals.get("currency")
        if sector or currency:
            ctx_line = (
                f"\nSector: {sector or 'unknown'} | Reporting currency: {currency or 'unknown'}\n"
            )

    return f"""Ticker: {ticker}
Question: {question}
{ctx_line}
Computed results — these are the only figures you may cite:
{facts_block}

Produce a single JSON object with these keys (exact names):
conviction_score (int 0-100),
stance (string: BUY|HOLD|SELL|WATCH),
investment_thesis (string: 3 to 6 sentences that answer the question, quoting
  the computed values each point rests on; say which needed values are missing),
bull_case (string: 1 to 3 sentences),
bear_case (string: 1 to 3 sentences),
key_risks (array of strings),
time_horizon (string, for example "6-12 months"),
confidence_in_data (int 1-5)

Every string must be written out. An empty field is not a cautious answer, it is
no answer: when the values are thin, say what they show and what is missing.
"""
