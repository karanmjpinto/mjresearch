"""Running your own checklists against this company's numbers.

Stage 04 could already tell you *which* of your frameworks touch a name. That
is the easy half and the less useful one: being told "your quality checklist is
relevant here" is a reminder, not an answer.

So this reads the criteria out of a framework note and puts this company's
figure next to each one. What it deliberately does not do is decide whether the
criterion passed.

That restraint is the whole design. A line like "owner-operator still involved"
or "pricing power a customer would grumble about but pay" is not a threshold, it
is a judgment, and a system that printed a green tick against it would be
inventing a verdict its inputs cannot support. Where a line *does* carry a
comparable number — "gross margin above 40%", "net debt under 2x EBITDA" — the
threshold is parsed and the comparison is made, because that one is arithmetic.
Everything else comes back with the company's relevant figure attached and no
opinion, which is what a checklist is for.

Three outcomes, and the distinction between the last two matters:

  ``met`` / ``missed``   a threshold was stated and the number is in hand
  ``unmatched``          no figure here speaks to this line, so nothing is said
  ``judgment``           the line asks for a view, not a measurement

Reporting `unmatched` separately from `judgment` keeps an honest gap from being
dressed up as depth. A checklist where nine of twelve lines are unmatched is
telling you this framework was written for something this data cannot see.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: Bullet, numbered or checkbox lines. A framework note is a list of criteria,
#: and those are the three ways people write a list.
_CRITERION = re.compile(r"^\s{0,6}(?:[-*+]|\d{1,2}[.)])\s+(?:\[[ xX]\]\s*)?(.+?)\s*$", re.M)

#: A heading, so a criterion can say which section of your framework it came
#: from rather than arriving as one flat list.
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", re.M)

#: Lines this short are section labels or stubs, not criteria.
MIN_CRITERION_CHARS = 8
#: Past this, it is prose that happens to start with a dash.
MAX_CRITERION_CHARS = 220
#: Enough of a checklist to be useful; beyond this it is a reference document.
MAX_CRITERIA = 40

#: A stated threshold: a comparison word, then a number, optionally a unit.
#: Only the forms that are unambiguous — "roughly around 40ish" is a judgment
#: wearing a number, and is left as one.
_THRESHOLD = re.compile(
    r"(?P<op>>=|<=|>|<|at least|no less than|above|over|greater than|"
    r"at most|no more than|below|under|less than|under|beneath)\s*"
    r"(?P<cur>[$€£])?\s*(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>%|x\b|bn\b|b\b|m\b)?",
    re.I,
)

_GREATER = {">=", ">", "at least", "no less than", "above", "over", "greater than"}

#: Words in a criterion → the metric that speaks to it. Deliberately a small,
#: explicit table rather than fuzzy matching: a wrong pairing here puts a real
#: number beside an unrelated sentence, which reads as evidence and is worse
#: than admitting the line is unmatched.
METRIC_WORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("gross margin",), "gross_margin"),
    (("operating margin", "ebit margin"), "operating_margin"),
    (("net margin", "profit margin"), "profit_margin"),
    (("free cash flow", "fcf"), "free_cash_flow"),
    (("revenue growth", "sales growth", "top line"), "revenue_growth"),
    (("return on equity", "roe"), "return_on_equity"),
    (("return on invested capital", "roic", "return on capital"), "return_on_capital"),
    (("net debt",), "net_debt"),
    (("total debt", "debt"), "total_debt"),
    (("debt to equity", "debt/equity", "gearing", "leverage"), "debt_to_equity"),
    (("interest coverage", "covers its interest"), "interest_coverage"),
    (("current ratio",), "current_ratio"),
    (("dividend yield",), "dividend_yield"),
    (("payout ratio",), "payout_ratio"),
    (("price to earnings", "p/e", "pe ratio", "earnings multiple"), "pe_ratio"),
    (("forward p/e", "forward pe"), "forward_pe"),
    (("price to book", "p/b", "book value"), "pb_ratio"),
    (("peg",), "peg_ratio"),
    (("beta", "volatility versus the market"), "beta"),
    (("market cap", "size of the company"), "market_cap"),
    (("revenue", "sales", "turnover"), "revenue"),
    (("insider ownership", "owner-operator", "founder"), None),
    (("moat", "switching cost", "pricing power", "brand"), None),
    (("management", "capital allocation", "incentives"), None),
)

#: Metrics quoted as percentages, so a 0.41 is shown as 41% and compared
#: against a "40%" threshold on the same footing.
FRACTION_METRICS = frozenset(
    {
        "gross_margin",
        "operating_margin",
        "profit_margin",
        "revenue_growth",
        "return_on_equity",
        "return_on_capital",
        "dividend_yield",
        "payout_ratio",
    }
)

#: Words that mark a line as asking for a view rather than a measurement, even
#: when a number happens to appear in it.
JUDGMENT_WORDS = (
    "moat",
    "management",
    "incentive",
    "culture",
    "trust",
    "honest",
    "story",
    "narrative",
    "understand",
    "circle of competence",
    "would i",
    "do i",
    "comfortable",
    "sleep",
)


@dataclass
class Criterion:
    """One line of a checklist, and what this company has to say about it."""

    text: str
    section: str | None = None
    verdict: str = "unmatched"  # met | missed | unmatched | judgment
    metric: str | None = None
    value: float | None = None
    display: str | None = None
    threshold: float | None = None
    comparison: str | None = None
    because: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "section": self.section,
            "verdict": self.verdict,
            "metric": self.metric,
            "value": self.value,
            "display": self.display,
            "threshold": self.threshold,
            "comparison": self.comparison,
            "because": self.because,
        }


@dataclass
class AppliedFramework:
    title: str
    path: str
    criteria: list[Criterion] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for c in self.criteria:
            counts[c.verdict] = counts.get(c.verdict, 0) + 1
        answerable = counts.get("met", 0) + counts.get("missed", 0)
        return {
            "title": self.title,
            "path": self.path,
            "criteria": [c.as_dict() for c in self.criteria],
            "counts": counts,
            "answerable": answerable,
            # The honest headline. A framework where two of fourteen lines can
            # be checked has not been "applied" in any meaningful sense, and
            # saying so is more useful than a score out of two.
            "finding": _finding(counts, len(self.criteria)),
        }


def _finding(counts: dict[str, int], total: int) -> str:
    met = counts.get("met", 0)
    missed = counts.get("missed", 0)
    answerable = met + missed
    if total == 0:
        return "No checklist lines found in this note."
    if answerable == 0:
        return (
            f"None of the {total} lines here can be checked against the data on hand — "
            "this framework asks for judgments and figures nobody is reporting."
        )
    verdict = f"{met} of {answerable} checkable lines are met"
    rest = total - answerable
    if rest:
        verdict += f"; the other {rest} need a view rather than a number"
    return verdict + "."


def extract_criteria(body: str) -> list[Criterion]:
    """Pull the checklist out of a note, keeping which section each line sat in."""
    # Heading positions, so each criterion can be attributed to the last
    # heading above it rather than to the note as a whole.
    headings = [(m.start(), m.group(1).strip()) for m in _HEADING.finditer(body)]

    out: list[Criterion] = []
    for m in _CRITERION.finditer(body):
        text = _clean(m.group(1))
        if not (MIN_CRITERION_CHARS <= len(text) <= MAX_CRITERION_CHARS):
            continue
        section = None
        for pos, title in headings:
            if pos < m.start():
                section = title
            else:
                break
        out.append(Criterion(text=text, section=section))
        if len(out) >= MAX_CRITERIA:
            break
    return out


def _clean(text: str) -> str:
    """Strip the markup that carries no meaning once the line is out of context."""
    t = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), text)
    t = re.sub(r"\*\*|__|\*|`", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _metric_for(text: str) -> str | None:
    """The metric a line is about, or None when nothing here speaks to it.

    Longest phrase first, so "forward p/e" is not swallowed by "p/e" and
    "operating margin" is not swallowed by "margin".
    """
    low = text.lower()
    best: tuple[int, str | None] | None = None
    for words, metric in METRIC_WORDS:
        for w in words:
            if w in low and (best is None or len(w) > best[0]):
                best = (len(w), metric)
    return best[1] if best else None


def _looks_like_judgment(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in JUDGMENT_WORDS)


def _read_threshold(text: str) -> tuple[float, str] | None:
    """The number a line demands, and which side of it to be on."""
    m = _THRESHOLD.search(text)
    if not m:
        return None
    num = float(m.group("num"))
    unit = (m.group("unit") or "").lower()
    if unit in {"bn", "b"}:
        num *= 1e9
    elif unit == "m":
        num *= 1e6
    op = m.group("op").lower()
    return num, (">=" if op in _GREATER else "<=")


def _fmt(metric: str, value: float) -> str:
    if metric in FRACTION_METRICS:
        return f"{value * 100:.1f}%"
    if abs(value) >= 1e9:
        return f"{value / 1e9:.1f}bn"
    if abs(value) >= 1e6:
        return f"{value / 1e6:.0f}m"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def apply_framework(
    title: str,
    path: str,
    body: str,
    metrics: dict[str, Any],
) -> AppliedFramework:
    """Put this company's figures beside each line of one framework."""
    applied = AppliedFramework(title=title, path=path)

    for crit in extract_criteria(body):
        metric = _metric_for(crit.text)

        # A line asking for a view stays a judgment even when it cites a
        # number, because the number is not what it is asking about.
        if metric is None or _looks_like_judgment(crit.text):
            crit.verdict = "judgment" if _looks_like_judgment(crit.text) else "unmatched"
            crit.because = (
                "Asks for a view, not a measurement."
                if crit.verdict == "judgment"
                else "No figure here speaks to this line."
            )
            applied.criteria.append(crit)
            continue

        raw = metrics.get(metric)
        value = raw if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None
        if value is None:
            crit.metric = metric
            crit.verdict = "unmatched"
            crit.because = f"{metric.replace('_', ' ')} is not reported for this company."
            applied.criteria.append(crit)
            continue

        crit.metric = metric
        crit.value = round(float(value), 6)
        crit.display = _fmt(metric, float(value))

        bound = _read_threshold(crit.text)
        if bound is None:
            crit.verdict = "judgment"
            crit.because = (
                f"The line states no threshold, so this is the figure and the call is yours: "
                f"{metric.replace('_', ' ')} is {crit.display}."
            )
            applied.criteria.append(crit)
            continue

        target, comparison = bound
        # A percentage threshold is written as 40, and the metric is stored as
        # 0.41. Compare them in the same unit or every margin line fails.
        scale = 100.0 if metric in FRACTION_METRICS else 1.0
        shown = float(value) * scale
        crit.threshold = target
        crit.comparison = comparison
        ok = shown >= target if comparison == ">=" else shown <= target
        crit.verdict = "met" if ok else "missed"
        crit.because = (
            f"{metric.replace('_', ' ')} is {crit.display} against "
            f"{'at least' if comparison == '>=' else 'at most'} "
            f"{_fmt(metric, target / scale)}."
        )
        applied.criteria.append(crit)

    return applied
