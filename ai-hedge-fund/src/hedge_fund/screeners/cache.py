"""Screen results, computed once and kept.

A screen is not a question you ask, it is a list you consult. That distinction
is the whole reason this file exists: the screener page used to make you choose
a universe, press run, and wait — and the waiting is not incidental, it is
seven seconds per name against yfinance. Five hundred names is an hour. Nobody
opens a screen they have to commission first.

So the results are computed ahead of time and served instantly, the way a
screen actually gets used. Four consequences worth stating, because each one
is a decision:

**Dated, not live.** Every cache carries the timestamp it was built at, and
the API hands that to the reader rather than hiding it. A screen presented
without its date invites the assumption that it is current, which for a
quarterly-fundamentals screen is wrong the moment a company reports. Stale is
fine; stale and silent is not.

**Whole, or not written.** A refresh that dies two hundred names in leaves the
previous cache alone rather than replacing it with a partial one. A list of two
hundred S&P names looks exactly like a complete screen that found two hundred
passes, and there is nothing on screen to tell them apart.

**Errors are kept.** A name whose data could not be fetched is recorded as
such rather than dropped. Dropping it makes the screen look cleaner and quietly
turns "we could not check this" into "this did not qualify".

**Dated against the rules, not just the clock.** A cache also records a
fingerprint of the thresholds the screen applied, because `built_at` only
answers half the staleness question. Adding a market-cap band to the
compounder turned 398 of the 503 names in its cached S&P 500 run into
companies that would now be rejected on size — and the file still reported
them as passes, with a fresh date and nothing to indicate otherwise. See
`criteria.py`. A cache built under different rules is still served, because it
is real data, but it is labelled.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hedge_fund.screeners import criteria as screen_criteria

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "screens"

#: Past this, the API says so. Chosen against what the screens actually read:
#: quarterly fundamentals, which move four times a year, so a week-old screen
#: is still a fair list and a month-old one has probably missed a reporting
#: season.
STALE_AFTER_DAYS = 7

#: The screens that have a cache. Names match the endpoint paths.
SCREENS = (
    "yartseva",
    "acquisition-compounder",
    "bolton-contrarian",
    "kiyohara-handbook",
    "ellenbogen-two-act",
)


@dataclass(frozen=True)
class CachedScreen:
    screen: str
    universe: str
    built_at: str
    results: list[dict[str, Any]]
    requested: int
    errors: int
    duration_s: float
    #: The fingerprint of the screen's rules when this was built. None for a
    #: cache written before fingerprints existed, which is not the same thing
    #: as a mismatch and must not be reported as one.
    criteria: str | None = None

    @property
    def age_days(self) -> float:
        try:
            built = datetime.fromisoformat(self.built_at)
        except ValueError:
            return float("inf")
        if built.tzinfo is None:
            built = built.replace(tzinfo=UTC)
        return (datetime.now(UTC) - built).total_seconds() / 86_400

    @property
    def criteria_changed(self) -> bool:
        """Whether the screen's rules moved since this was computed.

        Two cases deliberately answer False. An unregistered screen has no
        fingerprint to compare against, and a cache from before fingerprints
        existed has none stored — in both the honest answer is "unknown", and
        `criteria_known` is what distinguishes it. Reporting unknown as
        changed would cry wolf on every pre-existing file; reporting it as
        unchanged would be the original bug. So the API sends both.
        """
        current = screen_criteria.fingerprint(self.screen)
        if current is None or self.criteria is None:
            return False
        return current != self.criteria

    def as_dict(self) -> dict[str, Any]:
        age = self.age_days
        current = screen_criteria.fingerprint(self.screen)
        return {
            "screen": self.screen,
            "universe": self.universe,
            "built_at": self.built_at,
            "age_days": round(age, 2) if age != float("inf") else None,
            "stale": age > STALE_AFTER_DAYS,
            "stale_after_days": STALE_AFTER_DAYS,
            # Two fields, not one. "The rules changed" and "we cannot tell
            # whether the rules changed" are different claims and a reader
            # deciding whether to act on a row needs to know which they have.
            "criteria": self.criteria,
            "criteria_current": current,
            "criteria_known": self.criteria is not None and current is not None,
            "criteria_changed": self.criteria_changed,
            "requested": self.requested,
            "errors": self.errors,
            "duration_s": round(self.duration_s, 1),
            "count": len(self.results),
            "results": self.results,
        }


def _path(screen: str, universe: str) -> Path:
    safe = f"{screen}--{universe}".replace("/", "-").replace("..", "-")
    return CACHE_DIR / f"{safe}.json"


def read(screen: str, universe: str) -> CachedScreen | None:
    """The last computed run, or None. Never raises on a bad file."""
    p = _path(screen, universe)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        # A corrupt cache is a missing cache. Refusing to serve the page
        # because a file half-wrote is the wrong trade.
        logger.warning("unreadable screen cache %s (%s)", p, exc)
        return None

    try:
        return CachedScreen(
            screen=raw["screen"],
            universe=raw["universe"],
            built_at=raw["built_at"],
            results=raw["results"],
            requested=int(raw.get("requested", 0)),
            errors=int(raw.get("errors", 0)),
            duration_s=float(raw.get("duration_s", 0.0)),
            # Absent in every cache written before fingerprints existed.
            # `.get` rather than `[...]`, so those keep loading and report
            # "unknown" rather than vanishing from the listing.
            criteria=raw.get("criteria"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("screen cache %s has an unexpected shape (%s)", p, exc)
        return None


def write(
    screen: str,
    universe: str,
    results: list[dict[str, Any]],
    *,
    requested: int,
    duration_s: float,
) -> Path:
    """Replace the cache atomically.

    Written to a temporary file in the same directory and renamed, so a reader
    never sees a half-written screen. `os.replace` is atomic within a
    filesystem; writing in place is not, and this file is read by a live API.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    errors = sum(1 for r in results if r.get("error"))
    payload = {
        "screen": screen,
        "universe": universe,
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "requested": requested,
        "errors": errors,
        "duration_s": round(duration_s, 1),
        # Recorded at write time, from the modules that just produced these
        # rows, so the stored hash always describes the run beside it.
        "criteria": screen_criteria.fingerprint(screen),
        "results": results,
    }

    target = _path(screen, universe)
    fd, tmp = tempfile.mkstemp(dir=str(CACHE_DIR), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=1, default=str)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise

    logger.info(
        "wrote %s screen for %s: %d results, %d errors, %.1fs",
        screen,
        universe,
        len(results),
        errors,
        duration_s,
    )
    return target


def available() -> list[dict[str, Any]]:
    """Every cache on disk, with its age. For telling a reader what is ready."""
    out: list[dict[str, Any]] = []
    if not CACHE_DIR.is_dir():
        return out
    for p in sorted(CACHE_DIR.glob("*.json")):
        if p.name.startswith("."):
            continue
        stem = p.stem
        if "--" not in stem:
            continue
        screen, universe = stem.split("--", 1)
        got = read(screen, universe)
        if got is None:
            continue
        d = got.as_dict()
        # The listing is a menu, not the data. Sending five hundred rows per
        # entry would make choosing a screen slower than running one.
        d.pop("results", None)
        out.append(d)
    return out
