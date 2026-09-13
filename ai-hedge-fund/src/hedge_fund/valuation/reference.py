"""Vendored market reference data.

The equity risk premium, country premiums and rating spreads are published by
Aswath Damodaran and refreshed on his schedule, not ours. They are committed
into `config/damodaran/` rather than fetched, for the same reason every run
carries a snapshot hash: a valuation that changes because a spreadsheet updated
overnight is not a valuation you can compare to last month's.

Each file carries its own `as_of` and the source it came from, so a number on
screen can always be traced to a dated file rather than to "the internet".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

REFERENCE_DIR = Path(__file__).resolve().parents[3] / "config" / "damodaran"


class ReferenceMissing(RuntimeError):
    """Reference data absent or unreadable — refuse rather than assume."""


@dataclass(frozen=True)
class CountryRisk:
    name: str
    region: str | None
    rating: str | None
    country_risk_premium: float | None
    total_erp: float | None


@dataclass(frozen=True)
class Reference:
    """Everything the cost-of-capital build-up needs, with its dates."""

    implied_erp: float
    erp_as_of_year: int
    tbond_rate: float
    countries: dict[str, CountryRisk]
    country_as_of: str
    rating_tables: dict[str, list[dict[str, Any]]]
    rating_as_of: str

    def country(self, name: str) -> CountryRisk | None:
        return self.countries.get(name.strip().lower())

    def as_of(self) -> dict[str, Any]:
        return {
            "equity_risk_premium": self.erp_as_of_year,
            "country_risk": self.country_as_of,
            "rating_spreads": self.rating_as_of,
        }


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ReferenceMissing(f"{path.name} is not present in config/damodaran") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ReferenceMissing(f"{path.name} could not be read: {exc}") from exc


@lru_cache(maxsize=4)
def load_reference(directory: str | None = None) -> Reference:
    """Read the vendored files. Cached: they only change when someone commits."""
    base = Path(directory) if directory else REFERENCE_DIR
    erp = _read(base / "erp.json")
    ctry = _read(base / "country_risk.json")
    rat = _read(base / "rating_spreads.json")

    countries = {
        name.strip().lower(): CountryRisk(
            name=name,
            region=row.get("region"),
            rating=row.get("rating"),
            country_risk_premium=row.get("country_risk_premium"),
            total_erp=row.get("total_erp"),
        )
        for name, row in (ctry.get("countries") or {}).items()
    }
    if not countries:
        raise ReferenceMissing("country_risk.json contains no countries")

    tables = {k: v.get("bands") or [] for k, v in (rat.get("tables") or {}).items()}
    if not any(tables.values()):
        raise ReferenceMissing("rating_spreads.json contains no rating bands")

    return Reference(
        implied_erp=float(erp["implied_erp"]),
        erp_as_of_year=int(erp["as_of_year"]),
        tbond_rate=float(erp["tbond_rate"]),
        countries=countries,
        country_as_of=str(ctry.get("as_of") or "unknown"),
        rating_tables=tables,
        rating_as_of=str(rat.get("as_of") or "unknown"),
    )
