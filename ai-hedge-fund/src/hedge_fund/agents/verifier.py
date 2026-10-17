"""Check numeric claims in generated prose against the snapshot that produced it.

The structured fields of an analysis are schema-validated, but the thesis body is
free text, and that is where invented numbers live: a plausible P/E, a price that
was never quoted, an RSI that drifted a few points during generation. Those are
the errors that survive review, because they read exactly like the true ones.

This is a deterministic pass, not a second model. It anchors on metric names,
reads the nearest number, and compares it to the snapshot within a per-metric
tolerance. Anything it cannot map is reported as unverifiable rather than wrong —
silence about a claim must never look like a passing check.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache
from dataclasses import asdict, dataclass, field
from typing import Any

# Multipliers for magnitude suffixes written in prose.
_SCALES: dict[str, float] = {
    "k": 1e3,
    "thousand": 1e3,
    "m": 1e6,
    "mm": 1e6,
    "million": 1e6,
    "b": 1e9,
    "bn": 1e9,
    "billion": 1e9,
    "t": 1e12,
    "tn": 1e12,
    "trillion": 1e12,
}

_NUMBER = re.compile(
    r"""
    # An explicit sign, but only when it is not the hyphen inside a compound
    # word: "30-day low of 302.25" must not read as negative 302.25.
    (?P<sign>(?<![A-Za-z0-9])-)?\s*
    (?P<currency>[$€£₺])?\s*
    (?P<value>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)
    \s*
    # The short forms must not swallow the first letter of the next word:
    # without the lookahead, "316.83 today" parses as 316.83 trillion.
    (?:(?P<scale>trillion|billion|million|thousand|bn|tn|mm|[kmbt])(?![A-Za-z]))?
    \s*
    (?P<suffix>%|x)?
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass
class MetricSpec:
    """How to find one metric in prose and where its true value lives."""

    name: str
    aliases: tuple[str, ...]
    paths: tuple[str, ...]
    tolerance_pct: float = 2.0
    tolerance_abs: float | None = None
    # Sources disagree on whether rates are fractions or percentages, so a claim
    # matching either reading is accepted rather than flagged as invented.
    percent_ambiguous: bool = False
    # Prose states direction in words ("fell 12%"), not sign, so the reading has
    # to pick the sign up from the surrounding verb.
    directional: bool = False
    unit: str = ""
    # For a metric whose alias is an ordinary word ("momentum", "30-day"), a
    # bare number nearby is far more often something else — an RSI reading, the
    # ends of a price range — than a change. Require the percent to be written.
    needs_percent: bool = False


METRIC_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec(
        "price",
        ("current price", "trading at", "share price", "last close", "price of", "closed at"),
        ("price.current",),
        tolerance_pct=1.0,
        unit="currency",
    ),
    MetricSpec(
        "pe_ratio",
        (
            "p/e",
            "pe ratio",
            "price-to-earnings",
            "price to earnings",
            "earnings multiple",
            "trailing p/e",
        ),
        ("fundamentals.pe_ratio", "computed.pe_ratio"),
        tolerance_pct=3.0,
        unit="x",
    ),
    MetricSpec(
        "forward_pe",
        ("forward p/e", "forward pe", "forward earnings multiple"),
        ("fundamentals.forward_pe",),
        tolerance_pct=3.0,
        unit="x",
    ),
    MetricSpec(
        "price_to_book",
        ("price-to-book", "price to book", "p/b"),
        ("fundamentals.price_to_book",),
        tolerance_pct=3.0,
        unit="x",
    ),
    MetricSpec(
        "peg_ratio",
        ("peg ratio", "peg"),
        ("fundamentals.peg_ratio",),
        tolerance_pct=5.0,
        unit="x",
    ),
    MetricSpec(
        "market_cap",
        ("market cap", "market capitalisation", "market capitalization"),
        ("fundamentals.market_cap",),
        tolerance_pct=3.0,
        unit="currency",
    ),
    MetricSpec(
        "rsi_14",
        ("rsi", "relative strength index"),
        ("technicals.rsi_14", "computed.rsi_14"),
        tolerance_abs=1.5,
        unit="index",
    ),
    MetricSpec(
        "beta",
        ("beta",),
        ("fundamentals.beta",),
        tolerance_pct=5.0,
    ),
    MetricSpec(
        "dividend_yield",
        ("dividend yield", "yields", "yield of"),
        ("fundamentals.dividend_yield",),
        tolerance_pct=10.0,
        percent_ambiguous=True,
        unit="%",
    ),
    MetricSpec(
        "change_30d_pct",
        ("30-day", "30 day", "over the past month", "past 30 days", "monthly change"),
        ("price.change_30d_pct",),
        tolerance_abs=0.6,
        directional=True,
        unit="%",
        needs_percent=True,
    ),
    MetricSpec(
        "high_30d",
        ("30-day high", "30 day high", "recent high", "period high"),
        ("price.high_30d",),
        tolerance_pct=1.0,
        unit="currency",
    ),
    MetricSpec(
        "low_30d",
        ("30-day low", "30 day low", "recent low", "period low"),
        ("price.low_30d",),
        tolerance_pct=1.0,
        unit="currency",
    ),
    MetricSpec(
        "week52_high",
        ("52-week high", "52 week high", "52w high"),
        ("fundamentals.52w_high",),
        tolerance_pct=1.0,
        unit="currency",
    ),
    MetricSpec(
        "week52_low",
        ("52-week low", "52 week low", "52w low"),
        ("fundamentals.52w_low",),
        tolerance_pct=1.0,
        unit="currency",
    ),
    MetricSpec(
        "sma_50",
        ("50-day moving average", "50 day moving average", "50-day sma", "sma 50"),
        ("technicals.sma_50",),
        tolerance_pct=1.0,
        unit="currency",
    ),
    MetricSpec(
        "sharpe_ratio",
        ("sharpe ratio", "sharpe"),
        ("computed.sharpe_ratio",),
        tolerance_abs=0.05,
    ),
    MetricSpec(
        "sortino_ratio",
        ("sortino ratio", "sortino"),
        ("computed.sortino_ratio",),
        tolerance_abs=0.05,
    ),
    MetricSpec(
        "annualized_volatility_pct",
        (
            "annualised volatility",
            "annualized volatility",
            "realised volatility",
            "realized volatility",
        ),
        ("computed.annualized_volatility_pct",),
        tolerance_abs=0.6,
        unit="%",
    ),
    MetricSpec(
        "momentum_pct",
        ("momentum",),
        ("computed.momentum_pct",),
        tolerance_abs=0.6,
        directional=True,
        unit="%",
        needs_percent=True,
    ),
    MetricSpec(
        "max_drawdown_pct",
        ("max drawdown", "maximum drawdown", "peak-to-trough"),
        ("computed.max_drawdown_pct",),
        tolerance_abs=0.6,
        directional=True,
        unit="%",
    ),
    MetricSpec(
        "valuation_score",
        ("valuation score", "composite score"),
        ("computed.valuation_score",),
        tolerance_abs=1.0,
    ),
    MetricSpec(
        "sma_200",
        ("200-day moving average", "200 day moving average", "200-day sma", "sma 200"),
        ("technicals.sma_200",),
        tolerance_pct=1.0,
        unit="currency",
    ),
)

# How far from a metric name a number may sit and still be read as that metric's
# value. Wide enough for "a P/E ratio of roughly 31", tight enough to avoid
# capturing the next clause's number.
PROXIMITY_CHARS = 45


@dataclass
class Claim:
    metric: str
    stated: float
    actual: float | None
    verdict: str  # verified | mismatch | unverifiable
    excerpt: str
    unit: str = ""
    delta_pct: float | None = None
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class VerificationReport:
    status: str
    checked: int = 0
    verified: int = 0
    mismatched: int = 0
    unverifiable: int = 0
    claims: list[dict[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@lru_cache(maxsize=512)
def _alias_pattern(alias: str) -> re.Pattern[str]:
    """Match an alias as a whole term, not as a substring.

    Without boundaries "pe ratio" matches inside "sharpe ratio", and a Sharpe
    value of -0.094 gets reported as a contradicted P/E. Observed in a live run.
    """
    return re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])")


def _resolve(snapshot: dict[str, Any], path: str) -> Any:
    node: Any = snapshot
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _parse_number(match: re.Match[str]) -> float | None:
    raw = match.group("value").replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    scale = (match.group("scale") or "").lower()
    if scale:
        value *= _SCALES.get(scale, 1.0)
    if match.group("sign"):
        value = -value
    return value


_NEGATIVE_WORDS = (
    "fell",
    "fall",
    "fallen",
    "down",
    "declin",
    "lost",
    "lose",
    "drop",
    "slid",
    "slipped",
    "sank",
    "shed",
    "off by",
    "lower",
    "retreat",
    "pulled back",
)
_POSITIVE_WORDS = (
    "rose",
    "rise",
    "risen",
    "up ",
    "gain",
    "climb",
    "advanc",
    "surged",
    "jumped",
    "rallied",
    "higher",
    "added",
)


def _read_direction(text: str, number_start: int, alias_start: int) -> int:
    """Return -1, +1, or 0 for the direction stated near a number."""
    window_start = max(0, min(number_start, alias_start) - 40)
    window = text[window_start : max(number_start, alias_start)].lower()
    neg = max((window.rfind(w) for w in _NEGATIVE_WORDS), default=-1)
    pos = max((window.rfind(w) for w in _POSITIVE_WORDS), default=-1)
    if neg < 0 and pos < 0:
        return 0
    return -1 if neg > pos else 1


@dataclass
class _NumberHit:
    value: float
    excerpt: str
    span: tuple[int, int]
    distance: int
    # Whether the sign was written in the text rather than inferred from prose.
    signed: bool = False
    # The words between the metric name and the number, lowercased. Where the
    # reading of the number is decided: "below 40" and "industry average of 25".
    between: str = ""
    # True when the number follows the metric name, the usual order.
    after: bool = True
    # The figure describes peers or an average rather than this company.
    other_subject: bool = False


# Prose usually writes the metric before its value ("P/E ratio of 31.2"), but not
# always ("fell 12% over the past month"). A penalty on preceding numbers makes
# the common order win without ruling out the reversed one.
BACKWARD_PENALTY = 8

# Where one statement ends and the next begins: a line break (the fields of an
# analysis and its risk bullets are joined with one) or the end of a sentence.
# A metric name is never read against a number on the far side of either.
# Observed: "Price near 52-week high with limited downside buffer" followed on
# the next line by "Elevated RSI (69.3)" reported a 52-week high of 6.
_BOUNDARY = re.compile(r"\n|[.!?;](?=\s+[A-Z(])")

# A number that counts time is a window, not a value: the 30 in "30-day", the
# 14 in "14-day RSI", the 3 in "over 3 years".
_DURATION = re.compile(r"\s*-?\s*(?:day|week|month|quarter|year|yr)s?\b|\s*d\b", re.IGNORECASE)

_PERCENT_WORD = re.compile(r"\s*(?:percent|pct|percentage)", re.IGNORECASE)

# Words that say the figure belongs to something other than the company:
# "vs industry average of ~25x", "peers trade at higher PEG ratios (1.5-2)".
# Read between the metric and its number.
_OTHER_SUBJECT = re.compile(
    r"\b(?:peers?|industry|sector|competitors?|rivals?|average|median|typical(?:ly)?|"
    r"historical(?:ly)?|benchmark)\b"
)
# The narrower set read *before* the metric name. "average" is left out there:
# it is half of "50-day moving average", which routinely precedes another metric.
_OTHER_SUBJECT_BEFORE = re.compile(r"\b(?:peers?|industry|sector|competitors?|rivals?)\b")

# "RSI below 40" states a bound, not a value, and is true of an RSI of 35.56.
_UPPER_BOUND = re.compile(r"\b(?:below|under|less than|lower than|at most|no more than)\b|<")
_LOWER_BOUND = re.compile(
    r"\b(?:above|more than|greater than|higher than|at least|exceeds?|exceeding)\b|>"
)


def _segment(text: str, alias_start: int, alias_end: int) -> tuple[int, int]:
    """The statement an alias sits in: from the previous boundary to the next."""
    seg_start = 0
    for m in _BOUNDARY.finditer(text, 0, alias_start):
        seg_start = m.end()
    nxt = _BOUNDARY.search(text, alias_end)
    return seg_start, (nxt.start() if nxt else len(text))


def _unit_fits(spec: MetricSpec, m: re.Match[str], text: str) -> bool:
    """Whether a number is written as the kind of thing this metric is.

    "Trading at 7.3x P/E" is a multiple, so it is not the share price however
    close it sits to "trading at". Without this the price claimed 7.3, and the
    P/E was left to take the next number along — the industry's.
    """
    suffix = (m.group("suffix") or "").lower()
    if suffix == "x" and spec.unit not in ("x", ""):
        return False
    if suffix == "%" and spec.unit != "%":
        return False
    if m.group("currency") and spec.unit != "currency":
        return False
    if spec.needs_percent and suffix != "%" and not _PERCENT_WORD.match(text, m.end()):
        return False
    return True


def _is_value(m: re.Match[str], text: str, alias_spans: list[tuple[int, int]]) -> bool:
    """Rule out digits that are not a stated value at all."""
    start, end = m.start("value"), m.end("value")
    # The tail of a longer number the search window cut in half.
    if start > 0 and text[start - 1].isdigit():
        return False
    if start > 1 and text[start - 1] in ".," and text[start - 2].isdigit():
        return False
    if _DURATION.match(text, end):
        return False
    # Part of a metric's own name: the 50 in "SMA 50", the 52 in "52-week high".
    return not _overlaps((start, end), alias_spans)


def _alias_between(lo: int, hi: int, alias_spans: list[tuple[int, int]]) -> bool:
    """Whether some metric's name sits wholly inside text[lo:hi]."""
    return any(lo <= s and e <= hi for s, e in alias_spans)


def _number_candidates(
    text: str,
    alias_end: int,
    alias_start: int,
    spec: MetricSpec,
    alias_spans: list[tuple[int, int]],
) -> list[_NumberHit]:
    """Numbers near an alias, best reading first.

    Searched within the alias's own statement, and on the whole text rather
    than a slice of it, so a number at the edge of the window is read entire
    or not at all.
    """
    seg_start, seg_end = _segment(text, alias_start, alias_end)
    # Only the alias's own clause: in "below sector average (~15x), forward PE
    # (10.19x)" the sector belongs to the figure before the comma.
    lead = text[max(seg_start, alias_start - PROXIMITY_CHARS) : alias_start].lower()
    lead = re.split(r"[,;:()]", lead)[-1]
    subject_before = bool(_OTHER_SUBJECT_BEFORE.search(lead))
    candidates: list[_NumberHit] = []

    for m in _NUMBER.finditer(text, alias_end, seg_end):
        if m.start("value") - alias_end >= PROXIMITY_CHARS:
            break
        if not _is_value(m, text, alias_spans) or not _unit_fits(spec, m, text):
            continue
        value = _parse_number(m)
        if value is None:
            continue
        if _alias_between(alias_end, m.start(), alias_spans):
            # Another metric is named nearer the number, so it is that one's:
            # "near a 30-day low with oversold technicals (RSI=20.84)".
            break
        between = text[alias_end : m.start()].lower()
        candidates.append(
            _NumberHit(
                value=value,
                excerpt=text[max(0, alias_start - 15) : m.end() + 2].strip(),
                span=(m.start(), m.end()),
                distance=m.start() - alias_end,
                signed=bool(m.group("sign")),
                between=between,
                after=True,
                other_subject=subject_before or bool(_OTHER_SUBJECT.search(between)),
            )
        )
        break

    before_start = max(seg_start, alias_start - PROXIMITY_CHARS)
    hits = [
        m
        for m in _NUMBER.finditer(text, before_start, alias_start)
        if _is_value(m, text, alias_spans) and _unit_fits(spec, m, text)
    ]
    if hits and not _alias_between(hits[-1].end(), alias_start, alias_spans):
        m = hits[-1]
        value = _parse_number(m)
        if value is not None:
            between = text[m.end() : alias_start].lower()
            # What the number itself was introduced as: "sector average (~15x)".
            intro = text[max(seg_start, m.start() - 25) : m.start()].lower()
            candidates.append(
                _NumberHit(
                    value=value,
                    excerpt=text[m.start() : alias_end + 5].strip(),
                    span=(m.start(), m.end()),
                    distance=(alias_start - m.end()) + BACKWARD_PENALTY,
                    signed=bool(m.group("sign")),
                    between=between,
                    after=False,
                    other_subject=bool(
                        _OTHER_SUBJECT.search(between) or _OTHER_SUBJECT_BEFORE.search(intro)
                    ),
                )
            )

    # A figure about this company beats a nearer one about its peers.
    return sorted(candidates, key=lambda c: (c.other_subject, c.distance))


def _within_tolerance(spec: MetricSpec, stated: float, actual: float) -> tuple[bool, float | None]:
    if spec.tolerance_abs is not None:
        return abs(stated - actual) <= spec.tolerance_abs, None
    if actual == 0:
        return stated == 0, None
    delta_pct = abs(stated - actual) / abs(actual) * 100.0
    return delta_pct <= spec.tolerance_pct, round(delta_pct, 2)


def _matches(
    spec: MetricSpec, stated: float, actual: float
) -> tuple[bool, float | None, str | None]:
    ok, delta = _within_tolerance(spec, stated, actual)
    if ok:
        return True, delta, None
    if spec.percent_ambiguous:
        for scaled, note in (
            (actual * 100.0, "read as percent"),
            (actual / 100.0, "read as fraction"),
        ):
            ok_alt, delta_alt = _within_tolerance(spec, stated, scaled)
            if ok_alt:
                return True, delta_alt, note
    return False, delta, None


def _overlaps(span: tuple[int, int], taken: list[tuple[int, int]]) -> bool:
    return any(not (span[1] <= s or span[0] >= e) for s, e in taken)


def _read_bound(hit: _NumberHit) -> str | None:
    """ "upper", "lower", or None when the number is stated as a value."""
    if not hit.after:
        return None
    if _UPPER_BOUND.search(hit.between):
        return "upper"
    if _LOWER_BOUND.search(hit.between):
        return "lower"
    return None


def extract_claims(text: str, snapshot: dict[str, Any]) -> list[Claim]:
    """Find metric claims in prose and check each against the snapshot.

    Longer aliases are resolved first so a specific metric ("30-day high") claims
    its number before a generic one ("30-day") can take it, and each number is
    consumed once so two metrics cannot both report the same figure.
    """
    if not text:
        return []
    lowered = text.lower()

    occurrences: list[tuple[int, int, int, MetricSpec]] = []
    for spec in METRIC_SPECS:
        for alias in spec.aliases:
            for m in re.finditer(_alias_pattern(alias), lowered):
                occurrences.append((len(alias), m.start(), m.end(), spec))
    # Longest alias wins; ties resolve left to right for stable output.
    occurrences.sort(key=lambda o: (-o[0], o[1]))

    alias_spans = [(o[1], o[2]) for o in occurrences]
    claimed_aliases: list[tuple[int, int]] = []
    claimed_numbers: list[tuple[int, int]] = []
    claims: list[Claim] = []
    seen: set[tuple[str, float]] = set()

    for _length, start, end, spec in occurrences:
        if _overlaps((start, end), claimed_aliases):
            continue
        # A number already claimed by a more specific metric is skipped, not
        # treated as the end of the search.
        hit = next(
            (
                c
                for c in _number_candidates(text, end, start, spec, alias_spans)
                if not _overlaps(c.span, claimed_numbers)
            ),
            None,
        )
        if hit is None:
            continue

        stated = hit.value
        # Only infer direction from surrounding verbs when the text did not
        # state a sign outright; "-4.48% change" needs no interpretation.
        if spec.directional and not hit.signed:
            direction = _read_direction(text, hit.span[0], start)
            if direction < 0:
                stated = -abs(stated)
            elif direction > 0:
                stated = abs(stated)

        dedupe = (spec.name, round(stated, 6))
        if dedupe in seen:
            continue

        claimed_aliases.append((start, end))
        claimed_numbers.append(hit.span)
        seen.add(dedupe)

        if hit.other_subject:
            # Not a claim about this company, so the snapshot cannot contradict
            # it — and cannot confirm it either. Reported, not dropped: silence
            # about a figure must never look like a passing check.
            claims.append(
                Claim(
                    metric=spec.name,
                    stated=stated,
                    actual=None,
                    verdict="unverifiable",
                    excerpt=hit.excerpt,
                    unit=spec.unit,
                    note="describes peers or an average, not this company",
                )
            )
            continue

        actual: float | None = None
        for path in spec.paths:
            actual = _as_float(_resolve(snapshot, path))
            if actual is not None:
                break

        if actual is None:
            claims.append(
                Claim(
                    metric=spec.name,
                    stated=stated,
                    actual=None,
                    verdict="unverifiable",
                    excerpt=hit.excerpt,
                    unit=spec.unit,
                    note="metric absent from snapshot",
                )
            )
            continue

        bound = _read_bound(hit) if not spec.directional else None
        if bound is not None:
            # "below 40" is true of 35.56 and false of 44; nearness is not the test.
            holds = actual < stated if bound == "upper" else actual > stated
            ok, delta, note = _matches(spec, stated, actual)
            ok, delta = (ok or holds), (None if holds else delta)
            note = f"read as {'an upper' if bound == 'upper' else 'a lower'} bound"
        else:
            ok, delta, note = _matches(spec, stated, actual)
        claims.append(
            Claim(
                metric=spec.name,
                stated=stated,
                actual=actual,
                verdict="verified" if ok else "mismatch",
                excerpt=hit.excerpt,
                unit=spec.unit,
                delta_pct=delta,
                note=note,
            )
        )

    claims.sort(key=lambda c: (c.metric, c.stated))
    return claims


# Fields of a model output whose prose is worth checking.
TEXT_FIELDS = ("investment_thesis", "bull_case", "bear_case")


def verify_analysis(analysis: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Verify every numeric claim in an analysis against its snapshot."""
    if not isinstance(analysis, dict):
        return VerificationReport(status="no_claims", messages=["no analysis to verify"]).as_dict()

    parts = [str(analysis.get(f) or "") for f in TEXT_FIELDS]
    risks = analysis.get("key_risks")
    if isinstance(risks, list):
        parts.extend(str(r) for r in risks)
    text = "\n".join(p for p in parts if p)

    claims = extract_claims(text, snapshot)
    verified = sum(1 for c in claims if c.verdict == "verified")
    mismatched = [c for c in claims if c.verdict == "mismatch"]
    unverifiable = sum(1 for c in claims if c.verdict == "unverifiable")

    messages = [
        f"{c.metric}: thesis says {c.stated:g}{'%' if c.unit == '%' else ''}, "
        f"snapshot says {c.actual:g}"
        for c in mismatched
    ]

    if not claims:
        status = "no_claims"
    elif mismatched:
        status = "mismatch"
    else:
        status = "clean"

    return VerificationReport(
        status=status,
        checked=len(claims),
        verified=verified,
        mismatched=len(mismatched),
        unverifiable=unverifiable,
        claims=[c.as_dict() for c in claims],
        messages=messages,
    ).as_dict()
