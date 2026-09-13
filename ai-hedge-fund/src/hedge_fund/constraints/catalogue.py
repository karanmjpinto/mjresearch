"""The curated constraint map, and the names sitting on each chokepoint.

Hand-vetted rather than derived, for the same reason the comparable-company
sets are: a constraint map assembled by keyword lands you in "Sorbent
Materials matches materials" territory, and a bottleneck nobody checked is
worse than no map because it looks like work. Every entry carries where its
numbers came from, and an entry with no measurement is kept and shown as
unvalidated rather than quietly dropped — the gaps are the research queue.

Exposure is a stated band with a reason, never a computed score. Whether a
company is a pure play on precision reducers is a judgment about its business,
and dressing it as 0.82 would only hide who made the call.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from hedge_fund.constraints.validate import (
    Leg,
    Measurement,
    Route,
    binding_leg,
    capture_leg,
    durability_leg,
    validate,
)

logger = logging.getLogger(__name__)

CATALOGUE_PATH = Path(__file__).resolve().parents[3] / "config" / "constraints.json"

#: Whether a constraint is still a live candidate or has been answered in the
#: negative. Rejections stay in the file: deleting one loses the work and the
#: same idea comes back next quarter wearing the same story.
VERDICTS = ("open", "rejected")

#: The three systems, in the order they are shown. Named here so a typo in the
#: data file is a load error rather than a fourth column nobody notices.
SYSTEMS = ("intelligence", "power", "motion")

#: How concentrated a company's exposure is. Ordered best-first: a pure play on
#: the chokepoint transmits the whole squeeze, a conglomerate dilutes it into
#: noise. This ordering *is* the ranking.
EXPOSURE_BANDS = ("pure", "major", "minor")

#: What each band means, printed next to the name so the ranking is auditable.
BAND_MEANING = {
    "pure": "substantially all of the business sits on this chokepoint",
    "major": "a material segment, big enough to move the whole company",
    "minor": "real exposure, too small to move the whole company",
}


class CatalogueError(ValueError):
    """The constraint file could not be used. The caller is told which entry."""


@dataclass
class Name:
    """One listed company on a chokepoint, and how it is exposed."""

    ticker: str
    name: str
    exposure: str
    band: str
    revenue_share_pct: float | None = None
    source: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "exposure": self.exposure,
            "band": self.band,
            "band_means": BAND_MEANING[self.band],
            "revenue_share_pct": self.revenue_share_pct,
            "source": self.source,
        }


@dataclass
class Constraint:
    id: str
    system: str
    name: str
    scarce_object: str
    why: str
    measurements: list[Measurement] = field(default_factory=list)
    routes: list[Route] = field(default_factory=list)
    capture: dict[str, Any] = field(default_factory=dict)
    names: list[Name] = field(default_factory=list)
    #: "open" while it is still a live candidate, "rejected" once the evidence
    #: has answered it in the negative. Rejections are kept rather than deleted:
    #: a checked-and-dismissed constraint is one of the more valuable things a
    #: research tool can remember, because otherwise the same idea arrives again
    #: next quarter wearing the same story and gets re-researched from scratch.
    verdict: str = "open"
    rejected_because: str = ""

    def legs(self) -> list[Leg]:
        return [
            binding_leg(self.measurements),
            durability_leg(self.routes),
            capture_leg(
                share_pct=self.capture.get("share_pct"),
                pricing_power=self.capture.get("pricing_power"),
                pricing_evidence=self.capture.get("pricing_evidence", ""),
                rent_mechanism=self.capture.get("rent_mechanism", "concentration"),
            ),
        ]

    def ranked_names(self) -> list[Name]:
        """Purest exposure first — a pure play transmits the squeeze, a
        conglomerate dilutes it. Within a band, a sourced revenue share breaks
        the tie; an unsourced one sorts last rather than being guessed at."""
        return sorted(
            self.names,
            key=lambda n: (
                EXPOSURE_BANDS.index(n.band),
                -(n.revenue_share_pct if n.revenue_share_pct is not None else -1.0),
                n.ticker,
            ),
        )

    def as_dict(self, *, with_names: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "system": self.system,
            "name": self.name,
            "scarce_object": self.scarce_object,
            "why": self.why,
            "source": "curated",
            "verdict": self.verdict,
            "rejected_because": self.rejected_because,
            "validation": validate(self.legs()),
            "measurements": [m.as_dict() for m in self.measurements],
            "routes": [r.as_dict() for r in self.routes],
            "capture": self.capture,
            "name_count": len(self.names),
        }
        if with_names:
            out["names"] = [n.as_dict() for n in self.ranked_names()]
        return out


def _parse_name(raw: dict[str, Any], where: str) -> Name:
    band = str(raw.get("band", "")).strip().lower()
    if band not in EXPOSURE_BANDS:
        raise CatalogueError(
            f"{where}: name {raw.get('ticker')!r} has band {band!r}; "
            f"expected one of {', '.join(EXPOSURE_BANDS)}"
        )
    for required in ("ticker", "name", "exposure"):
        if not str(raw.get(required, "")).strip():
            raise CatalogueError(f"{where}: name {raw.get('ticker')!r} is missing {required!r}")
    return Name(
        ticker=str(raw["ticker"]).strip().upper(),
        name=str(raw["name"]).strip(),
        exposure=str(raw["exposure"]).strip(),
        band=band,
        revenue_share_pct=raw.get("revenue_share_pct"),
        source=str(raw.get("source", "")).strip(),
    )


def _parse_constraint(raw: dict[str, Any]) -> Constraint:
    cid = str(raw.get("id", "")).strip()
    if not cid:
        raise CatalogueError("a constraint has no id")
    where = f"constraint {cid!r}"

    system = str(raw.get("system", "")).strip().lower()
    if system not in SYSTEMS:
        raise CatalogueError(f"{where}: system {system!r}; expected one of {', '.join(SYSTEMS)}")

    for required in ("name", "scarce_object", "why"):
        if not str(raw.get(required, "")).strip():
            raise CatalogueError(f"{where}: missing {required!r}")

    verdict = str(raw.get("verdict", "open")).strip().lower()
    if verdict not in VERDICTS:
        raise CatalogueError(f"{where}: verdict {verdict!r}; expected one of {', '.join(VERDICTS)}")
    rejected_because = str(raw.get("rejected_because", "")).strip()
    if verdict == "rejected" and not rejected_because:
        # A rejection with no reason is worse than no rejection: it tells the
        # next reader the idea was dismissed without telling them why, so they
        # cannot tell a real finding from someone's hunch.
        raise CatalogueError(f"{where}: verdict 'rejected' needs rejected_because")

    return Constraint(
        id=cid,
        verdict=verdict,
        rejected_because=rejected_because,
        system=system,
        name=str(raw["name"]).strip(),
        scarce_object=str(raw["scarce_object"]).strip(),
        why=str(raw["why"]).strip(),
        measurements=[
            Measurement(
                metric=str(m["metric"]),
                value=float(m["value"]),
                unit=str(m["unit"]),
                as_of=str(m["as_of"]),
                source=str(m.get("source", "")),
                normal=m.get("normal"),
                note=str(m.get("note", "")),
            )
            for m in raw.get("measurements", [])
        ],
        routes=[
            Route(
                path=str(r["path"]),
                status=str(r["status"]).strip().lower(),
                eta_months=r.get("eta_months"),
                source=str(r.get("source", "")),
                note=str(r.get("note", "")),
            )
            for r in raw.get("routes", [])
        ],
        capture=dict(raw.get("capture", {})),
        names=[_parse_name(n, where) for n in raw.get("names", [])],
    )


@lru_cache(maxsize=1)
def load_catalogue(path: Path | None = None) -> tuple[Constraint, ...]:
    """Every curated constraint, or an empty tuple when there is no file.

    A missing file is a state, not a crash: the vault-derived column still
    works, and the page says the curated map is not installed.
    """
    target = path or CATALOGUE_PATH
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.info("no curated constraint map at %s", target)
        return ()
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogueError(f"could not read {target}: {exc}") from exc

    entries = raw.get("constraints", raw if isinstance(raw, list) else [])
    out = [_parse_constraint(e) for e in entries]

    seen: set[str] = set()
    for c in out:
        if c.id in seen:
            raise CatalogueError(f"duplicate constraint id {c.id!r}")
        seen.add(c.id)

    return tuple(out)


def by_id(cid: str, path: Path | None = None) -> Constraint | None:
    key = cid.strip().lower()
    return next((c for c in load_catalogue(path) if c.id.lower() == key), None)


def live(path: Path | None = None) -> tuple[Constraint, ...]:
    """Constraints still worth checking."""
    return tuple(c for c in load_catalogue(path) if c.verdict == "open")


def rejected(path: Path | None = None) -> tuple[Constraint, ...]:
    """Constraints already answered in the negative, kept as the negative result."""
    return tuple(c for c in load_catalogue(path) if c.verdict == "rejected")
