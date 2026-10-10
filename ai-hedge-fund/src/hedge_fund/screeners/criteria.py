"""What each screen tests, as data, and a fingerprint over it.

This exists because of a failure that was invisible by construction. A cached
screen recorded *when* it was built but not *what it was built against*, so
changing a threshold left every cache on disk looking perfectly healthy while
describing a screen that no longer existed. Adding a market-cap band to the
compounder silently turned 398 of the 503 names in its S&P 500 cache into
companies that would now be rejected on size — and the cache still reported
them as having passed, with a recent date and no warning anywhere.

That is precisely the failure this project exists to refuse. A screen that
says "built today, 61 passed" when the criteria moved underneath it is
reporting unverified work as verified.

So every screen registers the constants that decide its output, and the cache
stores a hash of them. A cache built under different criteria is still served
— it is real data and throwing it away helps nobody — but it is *labelled*,
the same way a stale one is. Stale is fine; stale and silent is not.

**The registry is checked, not trusted.** `tests/test_screen_criteria.py`
walks each screen module for module-level threshold constants and fails if one
is not registered here. Without that, this file degrades into a thing people
forget to update, and a fingerprint that silently stops covering a threshold
is worse than no fingerprint, because it actively asserts that nothing changed.

Deliberately *not* fingerprinted: the data provider's figures. Those change
constantly and are what `built_at` is for. This covers the screen's own rules.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from hedge_fund.screeners import (
    acquisition_compounder as ac,
)
from hedge_fund.screeners import (
    principles as pr,
)
from hedge_fund.screeners import (
    bolton_contrarian as bc,
)
from hedge_fund.screeners import (
    ellenbogen_two_act as et,
)
from hedge_fund.screeners import (
    kiyohara_handbook as kh,
)
from hedge_fund.screeners import (
    yartseva as yz,
)


def _shared() -> dict[str, Any]:
    """Rules every screen applies, so every fingerprint moves when they do.

    The standing exclusions are desk principles rather than screen rules, but
    they change what a screen returns, which is the only test for whether
    something belongs in the fingerprint. Adding a vice exclusion silently
    re-scores every cached run otherwise.
    """
    return {f"exclusion:{pid}": pat.pattern for pid, pat in pr.EXCLUSION_PATTERNS.items()}


def _compounder() -> dict[str, Any]:
    return {
        **_shared(),
        "min_rev_cagr_5y": ac.MIN_REV_CAGR_5Y,
        "min_eps_or_fcfps_cagr_5y": ac.MIN_EPS_OR_FCFPS_CAGR_5Y,
        "min_rev_yoy_proxy": ac.MIN_REV_YOY_PROXY,
        "min_roic": ac.MIN_ROIC,
        "min_fcf_conversion": ac.MIN_FCF_CONVERSION,
        "max_net_debt_to_ebitda": ac.MAX_NET_DEBT_TO_EBITDA,
        "min_interest_coverage": ac.MIN_INTEREST_COVERAGE,
        "max_share_cagr_5y": ac.MAX_SHARE_CAGR_5Y,
        "cap_band_by_currency": ac.CAP_BAND_BY_CURRENCY,
        "min_ic_growth_for_roiic": ac.MIN_IC_GROWTH_FOR_ROIIC,
        "reinvest_score_lo": ac.REINVEST_SCORE_LO,
        "reinvest_score_hi": ac.REINVEST_SCORE_HI,
        "t2_min_rev_cagr": ac.T2_MIN_REV_CAGR,
        "t2_min_fcf_margin": ac.T2_MIN_FCF_MARGIN,
        "t2_min_roic": ac.T2_MIN_ROIC,
        "t2_max_leverage": ac.T2_MAX_LEVERAGE,
        "rf_max_rev_yoy": ac.RF_MAX_REV_YOY,
        "rf_min_fcf_conv": ac.RF_MIN_FCF_CONV,
        "rf_max_leverage": ac.RF_MAX_LEVERAGE,
        "rf_max_dilution_cagr": ac.RF_MAX_DILUTION_CAGR,
        "avoid_industry_patterns": ac.AVOID_INDUSTRY_PATTERNS.pattern,
        "prefer_industry_patterns": ac.PREFER_INDUSTRY_PATTERNS.pattern,
    }


def _yartseva() -> dict[str, Any]:
    return {
        **_shared(),
        "mcap_min": yz.MCAP_MIN,
        "mcap_max": yz.MCAP_MAX,
        "excluded_sectors": sorted(yz.EXCLUDED_SECTORS),
        "composite_weights": yz.COMPOSITE_WEIGHTS,
    }


def _bolton() -> dict[str, Any]:
    return {
        **_shared(),
        "min_market_cap": bc.MIN_MARKET_CAP,
        "cheap_pe": bc.CHEAP_PE,
        "cheap_pb": bc.CHEAP_PB,
        "cheap_ev_ebitda": bc.CHEAP_EV_EBITDA,
        "cheap_p_fcf": bc.CHEAP_P_FCF,
        "max_debt_to_equity_hard": bc.MAX_DEBT_TO_EQUITY_HARD,
        "min_interest_cover_hard": bc.MIN_INTEREST_COVER_HARD,
        "max_range_position": bc.MAX_RANGE_POSITION,
        "pref_debt_to_equity": bc.PREF_DEBT_TO_EQUITY,
        "pref_interest_cover": bc.PREF_INTEREST_COVER,
        "pref_short_interest": bc.PREF_SHORT_INTEREST,
        "low_analyst_coverage": bc.LOW_ANALYST_COVERAGE,
        "insider_lookback_days": bc.INSIDER_LOOKBACK_DAYS,
    }


def _kiyohara() -> dict[str, Any]:
    return {
        **_shared(),
        "pe_tiers": kh.PE_TIERS,
        "pe_ceiling_max": kh.PE_CEILING_MAX,
        "real_estate_pe_ceiling": kh.REAL_ESTATE_PE_CEILING,
        "real_estate_sectors": kh.REAL_ESTATE_SECTORS,
        "min_equity_ratio": kh.MIN_EQUITY_RATIO,
        "pref_equity_ratio": kh.PREF_EQUITY_RATIO,
        "pref_net_cash_ratio": kh.PREF_NET_CASH_RATIO,
        "issuance_share_growth": kh.ISSUANCE_SHARE_GROWTH,
        "share_history_years": kh.SHARE_HISTORY_YEARS,
        "min_market_cap_by_currency": kh.MIN_MARKET_CAP_BY_CURRENCY,
    }


def _ellenbogen() -> dict[str, Any]:
    return {
        **_shared(),
        "compounder_cagr": et.COMPOUNDER_CAGR,
        "compounder_window_years": et.COMPOUNDER_WINDOW_YEARS,
        "min_rev_cagr": et.MIN_REV_CAGR,
        "min_rev_yoy": et.MIN_REV_YOY,
        "min_ebit_margin": et.MIN_EBIT_MARGIN,
        "proven_ebit_margin": et.PROVEN_EBIT_MARGIN,
        "min_gross_margin": et.MIN_GROSS_MARGIN,
        "pref_gross_margin": et.PREF_GROSS_MARGIN,
        "min_roic": et.MIN_ROIC,
        "pref_roic": et.PREF_ROIC,
        "roic_slope_best_pp": et.ROIC_SLOPE_BEST_PP,
        "roic_slope_worst_pp": et.ROIC_SLOPE_WORST_PP,
        "min_rev_growth_to_judge_slope": et.MIN_REV_GROWTH_TO_JUDGE_SLOPE,
        "max_ic_shrink_to_judge_slope": et.MAX_IC_SHRINK_TO_JUDGE_SLOPE,
        "min_ic_to_revenue_to_judge_roic": et.MIN_IC_TO_REVENUE_TO_JUDGE_ROIC,
        "reinvest_score_lo": et.REINVEST_SCORE_LO,
        "reinvest_score_hi": et.REINVEST_SCORE_HI,
        "max_share_cagr": et.MAX_SHARE_CAGR,
        "pref_share_cagr": et.PREF_SHARE_CAGR,
        "share_history_years": et.SHARE_HISTORY_YEARS,
        "pref_insider_stake": et.PREF_INSIDER_STAKE,
        "cap_band_by_currency": et.CAP_BAND_BY_CURRENCY,
        # Reported rather than scored, and still in the fingerprint: moving
        # either threshold changes which rows carry the transition flag, and a
        # cache whose flags were set under a different definition is exactly
        # the kind of silently-stale file this hash exists to label.
        "transition_drawdown": et.TRANSITION_DRAWDOWN,
        "structural_drawdown": et.STRUCTURAL_DRAWDOWN,
        "drawdown_lookback": et.DRAWDOWN_LOOKBACK,
    }


#: Screen name (as the endpoint spells it) → the rules it applies.
#:
#: Callables rather than literals so the values are read from the modules at
#: call time. A snapshot taken at import would be a copy, and a copy is a
#: second place for the number to live — which is the bug this file is for.
REGISTRY: dict[str, Any] = {
    "acquisition-compounder": _compounder,
    "yartseva": _yartseva,
    "bolton-contrarian": _bolton,
    "kiyohara-handbook": _kiyohara,
    "ellenbogen-two-act": _ellenbogen,
}


def criteria_for(screen: str) -> dict[str, Any] | None:
    """The rules a screen currently applies, or None if it has none registered."""
    build = REGISTRY.get(screen)
    return build() if build else None


def fingerprint(screen: str) -> str | None:
    """A short stable hash of a screen's rules, or None for an unknown screen.

    Sorted keys and a fixed separator, so the hash depends on the values and
    not on dict ordering or whitespace. Tuples serialise as lists, which is
    fine — the hash only has to be stable and sensitive, not reversible.

    Truncated to 12 hex characters. This is a change detector, not a security
    boundary: nobody is constructing a second set of thresholds that collides.
    """
    crit = criteria_for(screen)
    if crit is None:
        return None
    blob = json.dumps(crit, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]
