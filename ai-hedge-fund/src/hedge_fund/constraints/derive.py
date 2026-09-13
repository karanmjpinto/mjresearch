"""Constraints you have already noticed, pulled out of your own notes.

This does not discover bottlenecks. It finds the subjects *you* have written
about in constraint language more than once, and hands each one the three
questions it would have to answer to become investable. That distinction is
the whole design: a derived candidate arrives explicitly unvalidated, carrying
the notes that produced it, so you can see in one glance whether the tool found
a real thread in your thinking or two words that happened to co-occur.

Anything stronger would be dishonest. There is no measurement in a note — a
paragraph saying transformers are hard to get is not a lead time — so a derived
candidate never receives a score. It receives a research queue.

One note is not a thread. A subject has to appear in several notes, at least
one of them written in constraint language, before it is worth showing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from hedge_fund.knowledge.vault import Note, VaultIndex

#: Language that marks a note as being about something not being available.
#: Deliberately about *scarcity*, not about growth: "demand", "boom" and
#: "opportunity" appear in every bullish note ever written and would turn this
#: into a list of everything.
CONSTRAINT_TERMS = (
    "bottleneck",
    "chokepoint",
    "choke point",
    "shortage",
    "lead time",
    "lead-time",
    "sold out",
    "sold-out",
    "constrained",
    "constraint",
    "capacity limit",
    "supply limit",
    "allocation",
    "backlog",
    "scarcity",
    "scarce",
    "single source",
    "sole source",
    "export control",
    "rate limiting",
    "rate-limiting",
    "limiting factor",
)

#: Tags too broad to be a subject. A tag shared by half the vault describes the
#: vault, not a constraint.
_BROAD_TAGS = {
    "investing",
    "research",
    "notes",
    "wip",
    "moc",
    "idea",
    "ideas",
    "reading",
    "clipping",
    "clippings",
    "todo",
    "inbox",
    "thoughts",
    # Grammar and filing artefacts that end up as tags in a large vault.
    "the",
    "and",
    "for",
    "misc",
    "general",
    # Real subjects, but far too broad to be a chokepoint. A constraint is a
    # specific scarce object, not a continent or an asset class.
    "markets",
    "macro",
    "economics",
    "geopolitics",
    "infrastructure",
    "thesis",
    "diligence",
    "hardware",
}

#: How many notes a subject needs before it is worth proposing. Three was too
#: few: a tag with three notes that all mention a shortage hits a perfect ratio
#: on no evidence at all, and outranked a nineteen-note thread on silver.
MIN_NOTES = 5

#: How many of those notes must actually use constraint language. One is
#: enough to make it a candidate; zero makes it just a topic you write about.
MIN_FLAGGED = 1

#: And what share of them. Without this, every tag in a large vault qualifies
#: on a single stray "backlog" — the first run proposed "boat", "macro" and
#: "economics" as bottlenecks, which is the unfalsifiable list this whole
#: module exists to avoid producing. Set near half deliberately: at 0.30 the
#: vault's structural tags (#deeptech, 48 of 147) cleared the bar on incidental
#: language and buried a 17-of-19 thread on silver. A constraint subject is one
#: where scarcity is what most of the notes are *about*.
MIN_FLAGGED_RATIO = 0.45

#: Cap on proposals. This is a starting queue to work through, not a feed.
MAX_CANDIDATES = 12


@dataclass
class Derived:
    """A subject from your notes that might be a constraint, and the open questions."""

    id: str
    subject: str
    # True totals, kept separate from the samples below. Ranking on the
    # truncated lists made every candidate report the sample cap and put the
    # ordering in tag-iteration order — which is to say, no ordering at all.
    note_count: int
    flagged_count: int
    notes: list[dict[str, str]] = field(default_factory=list)
    flagged_quotes: list[dict[str, str]] = field(default_factory=list)

    @property
    def flagged_ratio(self) -> float:
        return self.flagged_count / self.note_count if self.note_count else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "system": None,  # unknown: your notes do not sort themselves into three systems
            "name": self.subject,
            "source": "your notes",
            "why": (
                f"{self.flagged_count} of your {self.note_count} notes on this subject "
                f"write about it as a constraint."
            ),
            "note_count": self.note_count,
            "flagged_count": self.flagged_count,
            "flagged_ratio": round(self.flagged_ratio, 3),
            "notes": self.notes,
            "evidence_in_your_words": self.flagged_quotes,
            # Never scored. A note is not a measurement, and the honest output
            # of this path is a question list, not a number.
            "validation": {
                "available": False,
                "reason": "derived from your notes, which contain no measurements",
                "unanswered": ["binding", "durability", "capture"],
                "open_questions": [
                    "Is it binding now? Find a lead time, utilisation rate, backlog or price — with a date.",
                    "Can it be routed around? Name the substitute or the new capacity, and when it lands.",
                    "Who keeps the rent? Name the holder, its share, and a price rise it actually made stick.",
                ],
            },
        }


def _flagged_quote(note: Note) -> dict[str, str] | None:
    """The sentence in a note that uses constraint language, if any.

    Quoting the user's own sentence rather than reporting a match is the
    difference between "this note mentions a bottleneck" and showing them
    what they wrote, which is the only way to judge the hit in one read.

    It is also the cover for what this cannot do: no amount of term matching
    distinguishes "a real shortage" from "there is no shortage". The quote puts
    the sentence in front of you so a negation is obvious in one read, rather
    than silently inflating a candidate.
    """
    for term in CONSTRAINT_TERMS:
        # Whole words only. A bare substring search on "scarce" also fires on
        # "scarcely", which is a word people reach for to say the opposite.
        m = re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", note.haystack)
        if m is None:
            continue
        start = max(0, m.start() - 90)
        end = min(len(note.haystack), m.start() + 110)
        snippet = re.sub(r"\s+", " ", note.haystack[start:end]).strip()
        return {"title": note.title, "path": note.path, "term": term, "quote": f"…{snippet}…"}
    return None


def derive_candidates(
    index: VaultIndex,
    *,
    min_notes: int = MIN_NOTES,
    limit: int = MAX_CANDIDATES,
) -> list[Derived]:
    """Subjects in your vault written about as constraints, most-evidenced first.

    Grouped by tag rather than by inferred topic. A tag is a decision you made
    about what a note is about, which makes it the one grouping signal in a
    vault that is not guesswork — and it means a proposal can always be
    explained as "these are your #hbm notes" rather than as a similarity score.
    """
    flagged: dict[str, dict[str, str]] = {}
    by_tag: dict[str, list[Note]] = {}

    for note in index.notes:
        quote = _flagged_quote(note)
        if quote:
            flagged[note.path] = quote
        for tag in note.tags:
            t = tag.strip().lower()
            if len(t) < 3 or t in _BROAD_TAGS:
                continue
            by_tag.setdefault(t, []).append(note)

    out: list[Derived] = []
    for tag, notes in by_tag.items():
        if len(notes) < min_notes:
            continue
        quotes = [flagged[n.path] for n in notes if n.path in flagged]
        if len(quotes) < MIN_FLAGGED:
            continue
        # The share matters more than the count. One note in two hundred
        # mentioning a backlog says nothing about the subject; it says your
        # vault is large. A tag only reads as a constraint when a real fraction
        # of its notes are about something being unavailable.
        if len(quotes) / len(notes) < MIN_FLAGGED_RATIO:
            continue
        out.append(
            Derived(
                id=f"vault:{tag}",
                subject=tag.replace("-", " "),
                note_count=len(notes),
                flagged_count=len(quotes),
                notes=[{"title": n.title, "path": n.path} for n in notes[:12]],
                flagged_quotes=quotes[:4],
            )
        )

    # Volume times density. Neither alone orders this: ranking by count puts
    # the vault's biggest structural tags on top, and ranking by ratio is a
    # small-sample trap where 3-of-3 outranks 17-of-19 — unanimous on almost no
    # evidence. The product rewards a subject that is both well covered and
    # genuinely about scarcity, which is what a constraint thread looks like.
    out.sort(key=lambda d: (-d.flagged_count * d.flagged_ratio, -d.flagged_count, d.subject))
    return out[:limit]
