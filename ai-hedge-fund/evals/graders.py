"""Graders: the checkable half of "was this answer any good".

Every grader here returns a hard pass/fail with a reason, and every one of them
tests a contract the app itself already states — in `_JSON_RULES`, in a
persona's own preamble, or in the verifier. None of them scores taste, and none
of them asks a model to judge another model.

The discipline that makes this worth having: **a grader you cannot fail is not
a grader.** `tests/test_eval_harness.py` feeds each one an answer that should
pass and an answer that should fail, so a grader that silently always returns
True gets caught. That test is the reason to trust the numbers this produces.

What is deliberately NOT graded:
  - whether SELL was the *right* call on Kohl's. Nobody knows, and a golden set
    that pretends to know would be fabricated.
  - prose quality. Not checkable, and not what breaks.
  - conviction calibration in absolute terms — only its direction and its
    coherence with the stance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

#: The output rules the app states in `personas._JSON_RULES`. Kept here as the
#: numbers the graders enforce, so a change to the rules shows up as a failing
#: eval rather than as a silently weaker contract.
MAX_RISKS = 12
CONVICTION_MIN, CONVICTION_MAX = 0, 100
NEUTRAL = 50
STANCES = {"BUY", "HOLD", "SELL", "WATCH"}


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reason: str

    def __bool__(self) -> bool:  # lets a caller write `if verdict:`
        return self.passed


def ok(reason: str = "") -> Verdict:
    return Verdict(True, reason)


def fail(reason: str) -> Verdict:
    return Verdict(False, reason)


Grader = Callable[[dict[str, Any], dict[str, Any]], Verdict]
"""A grader takes (answer, context) and returns a Verdict.

`context` carries whatever the case needs to judge the answer — the snapshot it
was given, the persona id, the numbers the harness computed.
"""


# --- A. shape and internal coherence -----------------------------------


def schema_valid(answer: dict, _ctx: dict) -> Verdict:
    """The fields the UI reads must exist and be the right type."""
    missing = [
        k
        for k in ("stance", "conviction_score", "investment_thesis", "key_risks")
        if k not in answer
    ]
    if missing:
        return fail(f"missing fields: {missing}")
    if not isinstance(answer["conviction_score"], int):
        return fail(f"conviction_score is {type(answer['conviction_score']).__name__}, not int")
    if not isinstance(answer["key_risks"], list):
        return fail("key_risks is not a list")
    return ok()


def conviction_in_range(answer: dict, _ctx: dict) -> Verdict:
    c = answer.get("conviction_score")
    if not isinstance(c, int):
        return fail("conviction_score not an int")
    if not CONVICTION_MIN <= c <= CONVICTION_MAX:
        return fail(f"conviction {c} outside {CONVICTION_MIN}-{CONVICTION_MAX}")
    return ok(f"conviction {c}")


def stance_in_enum(answer: dict, _ctx: dict) -> Verdict:
    s = answer.get("stance")
    return ok(s) if s in STANCES else fail(f"stance {s!r} not one of {sorted(STANCES)}")


def stance_matches_conviction(answer: dict, _ctx: dict) -> Verdict:
    """A SELL at conviction 90 is not a defensible answer.

    The app's own scale says 0 is strong sell and 100 strong buy. The rules add
    "independent of stance label", which is a caution against deriving one
    mechanically from the other — not licence to contradict. So the contract is
    generous: only a stance on the wrong side of neutral fails, and the neutral
    value itself is allowed for either.
    """
    s, c = answer.get("stance"), answer.get("conviction_score")
    if s not in STANCES or not isinstance(c, int):
        return fail("cannot judge: stance or conviction malformed")
    if s == "SELL" and c > NEUTRAL:
        return fail(f"SELL with conviction {c} (above neutral) contradicts the scale")
    if s == "BUY" and c < NEUTRAL:
        return fail(f"BUY with conviction {c} (below neutral) contradicts the scale")
    return ok(f"{s} at {c}")


def risks_present_and_bounded(answer: dict, _ctx: dict) -> Verdict:
    r = answer.get("key_risks")
    if not isinstance(r, list) or not r:
        return fail("no key_risks returned")
    if len(r) > MAX_RISKS:
        return fail(f"{len(r)} risks exceeds the stated maximum of {MAX_RISKS}")
    if any(not str(x).strip() for x in r):
        return fail("a risk entry is blank")
    return ok(f"{len(r)} risks")


def thesis_is_substantial(answer: dict, _ctx: dict) -> Verdict:
    """Short enough to be a non-answer is a failure mode we have seen.

    A 3B model returned a 167-character thesis for a maximum-conviction BUY.
    That is not a thesis, it is a label.
    """
    t = str(answer.get("investment_thesis") or "")
    return ok(f"{len(t)} chars") if len(t) >= 200 else fail(f"thesis only {len(t)} chars")


# --- B. grounding in the data it was given -----------------------------


_NUM = re.compile(r"-?\$?\d[\d,]*\.?\d*%?")


def no_invented_magnitudes(answer: dict, ctx: dict) -> Verdict:
    """Every large number in the prose should appear in the snapshot.

    Deliberately narrow. Small integers ("3 years", "two segments") are
    ordinary prose and are ignored; percentages and money are where a
    hallucinated figure does damage. The app's verifier does a stricter
    version of this against computed facts — this is the eval's own check so a
    regression shows up here too.
    """
    haystack = ctx.get("snapshot_text") or ""
    if not haystack:
        return ok("no snapshot text supplied; skipped")
    thesis = str(answer.get("investment_thesis") or "")
    suspect: list[str] = []
    for raw in _NUM.findall(thesis):
        digits = raw.strip("$%").replace(",", "")
        try:
            val = float(digits)
        except ValueError:
            continue
        if abs(val) < 10:  # ordinary prose numbers
            continue
        stem = digits.split(".")[0]
        if stem and stem not in haystack.replace(",", ""):
            suspect.append(raw)
    if suspect:
        return fail(f"figures absent from the snapshot: {suspect[:4]}")
    return ok()


def low_confidence_on_thin_data(answer: dict, ctx: dict) -> Verdict:
    """The rules require saying so when the data is thin. Hold them to it."""
    if not ctx.get("thin_data"):
        return ok("not a thin-data case")
    c = answer.get("confidence_in_data")
    if not isinstance(c, int):
        return fail("confidence_in_data missing on a thin-data case")
    return ok(f"confidence {c}") if c <= 3 else fail(f"confidence {c} too high for thin data")


# --- C. did the persona behave like itself -----------------------------


def not_a_high_conviction_buy(answer: dict, _ctx: dict) -> Verdict:
    """For cases where the investor's own framework rules the name out.

    Bolton on a company at 45x book sitting near its high is the clearest
    instance: his framework requires "unloved", and this is the opposite. The
    contract is directional — he may say HOLD, WATCH or SELL, and may even say
    BUY quietly — but a *high-conviction* BUY means the lens was ignored.
    """
    s, c = answer.get("stance"), answer.get("conviction_score")
    if s == "BUY" and isinstance(c, int) and c >= 70:
        return fail(f"high-conviction BUY ({c}) on a name the lens rules out")
    return ok(f"{s} at {c}")


def mentions_any(*needles: str) -> Grader:
    """The answer must engage with at least one named concept.

    Used where a persona's framework makes a topic unavoidable — Graham and
    negative book equity, say. Matched case-insensitively across the thesis and
    the risks, because either is a legitimate place to raise it.
    """

    def grader(answer: dict, _ctx: dict) -> Verdict:
        blob = " ".join(
            [
                str(answer.get("investment_thesis") or ""),
                *[str(x) for x in answer.get("key_risks") or []],
            ]
        ).lower()
        hit = [n for n in needles if n.lower() in blob]
        return (
            ok(f"mentioned {hit[0]!r}") if hit else fail(f"never mentions any of {list(needles)}")
        )

    return grader


def declines_or_hedges(answer: dict, _ctx: dict) -> Verdict:
    """Norbert Lou's whole discipline is that almost everything is a pass.

    A confident BUY from the punch-card lens on an ordinary name means the
    defining constraint of that persona was dropped. HOLD, WATCH, SELL or a
    modest BUY all pass.
    """
    s, c = answer.get("stance"), answer.get("conviction_score")
    if s == "BUY" and isinstance(c, int) and c >= 75:
        return fail(f"punch-card lens returned a {c}-conviction BUY; it should mostly pass")
    return ok(f"{s} at {c}")
