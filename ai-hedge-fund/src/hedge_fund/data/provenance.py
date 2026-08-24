"""Provider provenance — record which source answered, and verify what it returned.

Every fetch that reaches a provider (or is served from cache) is recorded against
the :class:`ProvenanceLog` bound to the current context. Callers opt in with
:func:`capture`; nothing else in the call chain needs to change, and ``asyncio``
fan-out inherits the same log because context is copied by reference into child
tasks.

The verification half exists because a fallback chain silently changes the source
under an analysis. Two providers rarely agree on split adjustment, fiscal-period
alignment, or currency, so a resolved series is not trustworthy until its shape
has been checked: frequency, date range, point count, and — where we can tell —
units and adjustment basis.
"""

from __future__ import annotations

import logging

import math
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from hedge_fund.data.cache import DataCategory

logger = logging.getLogger(__name__)

# Series whose values are ratios/multiples rather than currency amounts. Used to
# skip currency inference on fields where a bare number is expected.
_UNITLESS_FUNDAMENTAL_KEYS = frozenset(
    {
        "pe_ratio",
        "forward_pe",
        "peg_ratio",
        "price_to_book",
        "price_to_sales",
        "beta",
        "profit_margin",
        "operating_margin",
        "return_on_equity",
        "return_on_assets",
        "debt_to_equity",
        "current_ratio",
        "quick_ratio",
        "dividend_yield",
        "payout_ratio",
        "short_ratio",
    }
)


@dataclass
class SeriesChecks:
    """Shape verification for a resolved series or record.

    Every field is optional: a check that could not be evaluated stays ``None``
    rather than defaulting to a pass, so "unverified" is never mistaken for
    "verified good".
    """

    row_count: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    frequency: str | None = None
    gap_days_max: int | None = None
    currency: str | None = None
    adjusted: bool | None = None
    columns: list[str] | None = None
    non_finite_values: int | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, [], {})}


@dataclass
class ProviderMeta:
    """Who answered a single data request, when, and what shape the answer had."""

    category: str
    key: str
    provider: str | None
    from_cache: bool
    fetched_at: str
    served_at: str | None = None
    age_seconds: int | None = None
    params: dict[str, Any] = field(default_factory=dict)
    checks: dict[str, Any] = field(default_factory=dict)
    attempted: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def slot(self) -> str:
        return f"{self.category}:{self.key}"

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        return {k: v for k, v in out.items() if v not in (None, [], {})}


class ProvenanceLog:
    """Ordered record of every provider resolution during one unit of work."""

    def __init__(self) -> None:
        self.entries: list[ProviderMeta] = []

    def record(self, meta: ProviderMeta) -> None:
        self.entries.append(meta)

    def by_slot(self) -> dict[str, dict[str, Any]]:
        """Latest entry per ``category:key``, for embedding in a snapshot."""
        out: dict[str, dict[str, Any]] = {}
        for meta in self.entries:
            out[meta.slot] = meta.as_dict()
        return out

    def providers_used(self) -> list[str]:
        seen: list[str] = []
        for meta in self.entries:
            if meta.provider and meta.provider not in seen:
                seen.append(meta.provider)
        return seen

    def warnings(self) -> list[str]:
        """Flatten every verification warning, prefixed by the slot it came from."""
        out: list[str] = []
        for meta in self.entries:
            for w in meta.checks.get("warnings", []) or []:
                out.append(f"{meta.slot}: {w}")
            if meta.error:
                out.append(f"{meta.slot}: {meta.error}")
        return out

    def as_dict(self) -> dict[str, Any]:
        return {
            "slots": self.by_slot(),
            "providers_used": self.providers_used(),
            "warnings": self.warnings(),
            "fetch_count": len(self.entries),
            "cache_hits": sum(1 for m in self.entries if m.from_cache),
        }

    def __len__(self) -> int:
        return len(self.entries)


_active: ContextVar[ProvenanceLog | None] = ContextVar("hedge_fund_provenance", default=None)


@contextmanager
def capture() -> Iterator[ProvenanceLog]:
    """Collect provenance for every registry fetch inside this block."""
    log = ProvenanceLog()
    token = _active.set(log)
    try:
        yield log
    finally:
        _active.reset(token)


def active_log() -> ProvenanceLog | None:
    return _active.get()


def record(meta: ProviderMeta) -> None:
    """Append to the active log, if any. No-op when nothing is capturing."""
    log = _active.get()
    if log is not None:
        log.record(meta)


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_meta(
    category: DataCategory | str,
    key: str,
    *,
    provider: str | None,
    from_cache: bool,
    params: dict[str, Any] | None = None,
) -> ProviderMeta:
    cat = category.value if isinstance(category, DataCategory) else str(category)
    return ProviderMeta(
        category=cat,
        key=key,
        provider=provider,
        from_cache=from_cache,
        fetched_at=_utcnow_iso(),
        params={k: str(v) for k, v in (params or {}).items() if v is not None},
    )


# ----------------------------------------------------------------------
# Verification
# ----------------------------------------------------------------------


def _infer_frequency(index: Any) -> tuple[str | None, int | None]:
    """Return (frequency label, largest gap in days) for a datetime-like index."""
    try:
        import pandas as pd
    except ImportError:  # pragma: no cover - pandas is a hard dependency
        return None, None

    try:
        idx = pd.DatetimeIndex(pd.to_datetime(index))
    except Exception as exc:
        # Not a failure: a payload may legitimately carry a non-temporal index.
        # The caller reports the range as unknown, which is the honest answer.
        logger.debug("provenance: index is not date-like (%s)", exc)
        return None, None
    if len(idx) < 3:
        return None, None

    deltas = idx.to_series().diff().dropna().dt.total_seconds() / 86400.0
    if deltas.empty:
        return None, None
    median = float(deltas.median())
    gap_max = int(deltas.max())

    if median < 0.5:
        freq = "intraday"
    elif median <= 1.6:
        freq = "daily"
    elif median <= 4.5:
        freq = "business_daily"
    elif median <= 9.0:
        freq = "weekly"
    elif median <= 45.0:
        freq = "monthly"
    elif median <= 120.0:
        freq = "quarterly"
    else:
        freq = "annual"
    return freq, gap_max


def verify_price_frame(df: Any, *, expected_days: int | None = None) -> SeriesChecks:
    """Verify an OHLCV frame: shape, coverage, frequency, adjustment basis."""
    checks = SeriesChecks()
    try:
        import pandas as pd
    except ImportError:  # pragma: no cover
        return checks
    if not isinstance(df, pd.DataFrame):
        checks.warnings.append(f"expected a DataFrame, got {type(df).__name__}")
        return checks
    if df.empty:
        checks.row_count = 0
        checks.warnings.append("empty price frame")
        return checks

    checks.row_count = len(df)
    checks.columns = [str(c) for c in df.columns]

    idx = df.index
    try:
        dt_idx = pd.DatetimeIndex(pd.to_datetime(idx))
        checks.start_date = str(dt_idx.min().date())
        checks.end_date = str(dt_idx.max().date())
        if not dt_idx.is_monotonic_increasing:
            checks.warnings.append("price index is not sorted ascending")
        if dt_idx.has_duplicates:
            checks.warnings.append("price index contains duplicate timestamps")
    except Exception:
        checks.warnings.append("price index is not datetime-like")
        dt_idx = None

    if dt_idx is not None:
        freq, gap_max = _infer_frequency(dt_idx)
        checks.frequency = freq
        checks.gap_days_max = gap_max
        # 5 calendar days covers a normal weekend; 10 covers a holiday week.
        if gap_max is not None and gap_max > 10 and freq in ("daily", "business_daily"):
            checks.warnings.append(f"gap of {gap_max} days in a {freq} series")

    close_col = next((c for c in df.columns if str(c).lower() == "close"), None)
    if close_col is None:
        checks.warnings.append("no 'close' column")
    else:
        col = pd.to_numeric(df[close_col], errors="coerce")
        # to_numeric coerces junk to NaN but leaves inf intact, so count both.
        checks.non_finite_values = int((col.isna() | col.abs().eq(float("inf"))).sum())
        if checks.non_finite_values:
            checks.warnings.append(f"{checks.non_finite_values} non-finite close values")
        finite = col[col.notna() & col.abs().ne(float("inf"))]
        if (finite <= 0).any():
            checks.warnings.append("non-positive close values present")

    # Adjustment basis: an explicit adj close column means the raw close is
    # unadjusted; its absence means we cannot tell and must not guess.
    adj_col = next(
        (c for c in df.columns if str(c).lower().replace(" ", "_") in ("adj_close", "adjclose")),
        None,
    )
    if adj_col is not None:
        checks.adjusted = False
        checks.warnings.append(
            "frame carries a separate adjusted-close column — 'close' is unadjusted"
        )

    if expected_days is not None and checks.row_count is not None:
        # Trading days run ~69% of calendar days; flag only a serious shortfall.
        floor = max(2, int(expected_days * 0.45))
        if checks.row_count < floor:
            checks.warnings.append(f"only {checks.row_count} rows for a {expected_days}-day window")
    return checks


def verify_mapping(data: Any, *, category: str) -> SeriesChecks:
    """Verify a dict-shaped payload (fundamentals, technicals, …)."""
    checks = SeriesChecks()
    if not isinstance(data, dict):
        checks.warnings.append(f"expected a mapping, got {type(data).__name__}")
        return checks
    if data.get("error"):
        checks.warnings.append(f"provider reported: {data['error']}")
        return checks

    keys = [k for k in data.keys() if not str(k).startswith("_")]
    checks.columns = sorted(str(k) for k in keys)
    populated = sum(1 for k in keys if data.get(k) not in (None, "", [], {}))
    checks.row_count = populated
    if not populated:
        checks.warnings.append("all fields empty")

    non_finite = 0
    for k in keys:
        v = data.get(k)
        if isinstance(v, float) and not math.isfinite(v):
            non_finite += 1
    if non_finite:
        checks.non_finite_values = non_finite
        checks.warnings.append(f"{non_finite} non-finite numeric fields")

    cur = data.get("currency") or data.get("financial_currency")
    if isinstance(cur, str) and cur.strip():
        checks.currency = cur.strip().upper()
    elif category == DataCategory.FUNDAMENTALS.value:
        has_currency_amount = any(
            k not in _UNITLESS_FUNDAMENTAL_KEYS and isinstance(data.get(k), (int, float))
            for k in keys
        )
        if has_currency_amount:
            checks.warnings.append("currency not declared on a payload containing amounts")
    return checks


def verify_sequence(data: Any) -> SeriesChecks:
    """Verify a list payload (news, filings, peers, …)."""
    checks = SeriesChecks()
    if not isinstance(data, list):
        checks.warnings.append(f"expected a list, got {type(data).__name__}")
        return checks
    checks.row_count = len(data)
    if not data:
        checks.warnings.append("empty list")
    return checks


def verify(category: DataCategory | str, value: Any, **kwargs: Any) -> SeriesChecks:
    """Dispatch verification by category and payload shape."""
    cat = category.value if isinstance(category, DataCategory) else str(category)
    try:
        import pandas as pd

        if isinstance(value, pd.DataFrame):
            expected = kwargs.get("days")
            return verify_price_frame(value, expected_days=int(expected) if expected else None)
    except ImportError:  # pragma: no cover
        pass
    if isinstance(value, list):
        return verify_sequence(value)
    if isinstance(value, dict):
        return verify_mapping(value, category=cat)
    return SeriesChecks()
