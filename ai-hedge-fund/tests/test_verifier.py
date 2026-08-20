"""Numeric claim verification against the snapshot."""

from __future__ import annotations

import pytest

from hedge_fund.agents.verifier import extract_claims, verify_analysis

SNAP = {
    "price": {
        "current": 316.83,
        "change_30d_pct": -2.99,
        "high_30d": 340.08,
        "low_30d": 302.25,
    },
    "fundamentals": {
        "pe_ratio": 31.2,
        "forward_pe": 27.4,
        "market_cap": 4.7e12,
        "dividend_yield": 0.0044,
        "beta": 1.09,
        "price_to_book": 58.3,
        "52w_high": 355.0,
        "52w_low": 240.1,
    },
    "technicals": {"rsi_14": 47.3, "sma_50": 320.0, "sma_200": 295.5},
}


def _verdicts(text, snapshot=SNAP):
    return {c.metric: c.verdict for c in extract_claims(text, snapshot)}


def _claim(text, metric, snapshot=SNAP):
    for c in extract_claims(text, snapshot):
        if c.metric == metric:
            return c
    return None


# ----------------------------------------------------------------------
# Correct claims verify
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,metric",
    [
        ("The current price of 316.83 is elevated.", "price"),
        ("It is trading at $316.83 today.", "price"),
        ("A P/E ratio of 31.2 looks rich.", "pe_ratio"),
        ("The forward P/E of 27.4 is more reasonable.", "forward_pe"),
        ("Market cap is $4.7 trillion.", "market_cap"),
        ("Market cap of 4700 billion.", "market_cap"),
        ("The RSI of 47.3 is neutral.", "rsi_14"),
        ("Beta of 1.09 implies market-like risk.", "beta"),
        ("The 52-week high of 355.0 stands well above.", "week52_high"),
        ("The 52-week low of 240.1 marked the bottom.", "week52_low"),
        ("Its 200-day moving average of 295.5 is rising.", "sma_200"),
        ("Price-to-book of 58.3 is extreme.", "price_to_book"),
    ],
)
def test_accurate_claims_verify(text, metric):
    assert _verdicts(text).get(metric) == "verified"


def test_commas_and_currency_symbols_parse():
    assert _verdicts("The current price of $1,316.83", {"price": {"current": 1316.83}}) == {
        "price": "verified"
    }


def test_percent_ambiguity_accepts_either_reading():
    assert _verdicts("It yields 0.44%.")["dividend_yield"] == "verified"
    assert _verdicts("Dividend yield of 0.0044")["dividend_yield"] == "verified"


def test_tolerance_allows_reasonable_rounding():
    assert _verdicts("A P/E ratio of 31.")["pe_ratio"] == "verified"


# ----------------------------------------------------------------------
# Hallucinated claims are caught
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,metric",
    [
        ("A P/E ratio of 45 is unjustifiable.", "pe_ratio"),
        ("It is trading at $412.00 today.", "price"),
        ("The RSI of 82 signals an overbought market.", "rsi_14"),
        ("Market cap is $9.1 trillion.", "market_cap"),
        ("Beta of 2.4 means high risk.", "beta"),
    ],
)
def test_invented_numbers_are_flagged(text, metric):
    assert _verdicts(text).get(metric) == "mismatch"


def test_direction_words_set_the_sign():
    assert _claim("Shares fell 12% over the past month.", "change_30d_pct").stated == -12.0
    assert _claim("Shares rose 12% over the past month.", "change_30d_pct").stated == 12.0


def test_correct_negative_change_verifies():
    assert (
        _verdicts("The stock declined 2.99% over the past month.")["change_30d_pct"] == "verified"
    )


def test_sign_error_is_caught():
    """Right magnitude, wrong direction is still wrong."""
    assert _verdicts("The stock rose 2.99% over the past month.")["change_30d_pct"] == "mismatch"


# ----------------------------------------------------------------------
# Matcher precision
# ----------------------------------------------------------------------


def test_specific_alias_beats_generic_one():
    """'30-day high' must claim its number before '30-day' can."""
    v = _verdicts("The 30-day high of 340.08 was rejected.")
    assert v.get("high_30d") == "verified"
    assert "change_30d_pct" not in v


def test_a_number_is_not_claimed_by_two_metrics():
    claims = extract_claims("Shares fell 12% over the past month and the P/E of 45 is rich.", SNAP)
    stated = [(c.metric, c.stated) for c in claims]
    assert ("pe_ratio", 45.0) in stated
    assert ("change_30d_pct", -12.0) in stated
    assert len({c.stated for c in claims}) == len(claims)


def test_distant_numbers_are_not_attached():
    text = "The P/E ratio is a useful lens. " + "Filler text. " * 12 + "We note 999 elsewhere."
    assert not any(c.stated == 999 for c in extract_claims(text, SNAP))


def test_metric_absent_from_snapshot_is_unverifiable_not_wrong():
    claim = _claim("The PEG ratio of 2.1 is high.", "peg_ratio")
    assert claim is not None
    assert claim.verdict == "unverifiable"
    assert "absent from snapshot" in claim.note


def test_prose_with_no_numbers_yields_nothing():
    assert extract_claims("A high-quality franchise with durable advantages.", SNAP) == []


def test_extraction_is_deterministic():
    text = "Trading at $316.83 with a P/E ratio of 45 and an RSI of 47.3."
    assert [c.as_dict() for c in extract_claims(text, SNAP)] == [
        c.as_dict() for c in extract_claims(text, SNAP)
    ]


# ----------------------------------------------------------------------
# Report shape
# ----------------------------------------------------------------------


def test_report_counts_and_status():
    analysis = {
        "investment_thesis": "Trading at $316.83 with a P/E ratio of 31.2.",
        "bull_case": "The RSI of 47.3 is neutral.",
        "bear_case": "",
        "key_risks": [],
    }
    r = verify_analysis(analysis, SNAP)
    assert r["status"] == "clean"
    assert r["checked"] == 3
    assert r["verified"] == 3
    assert r["mismatched"] == 0


def test_report_flags_mismatch_with_a_message():
    analysis = {"investment_thesis": "A P/E ratio of 45.", "bull_case": "", "bear_case": ""}
    r = verify_analysis(analysis, SNAP)
    assert r["status"] == "mismatch"
    assert any("pe_ratio" in m for m in r["messages"])


def test_report_scans_key_risks_too():
    analysis = {
        "investment_thesis": "",
        "bull_case": "",
        "bear_case": "",
        "key_risks": ["An RSI of 82 signals froth."],
    }
    assert verify_analysis(analysis, SNAP)["mismatched"] == 1


def test_report_handles_empty_and_malformed_input():
    assert verify_analysis({}, SNAP)["status"] == "no_claims"
    assert verify_analysis(None, SNAP)["status"] == "no_claims"


def test_report_handles_empty_snapshot():
    analysis = {"investment_thesis": "A P/E ratio of 31.2."}
    r = verify_analysis(analysis, {})
    assert r["status"] == "no_claims" or r["unverifiable"] == r["checked"]


def test_non_finite_snapshot_values_are_treated_as_absent():
    snap = {"fundamentals": {"pe_ratio": float("nan")}}
    assert _claim("A P/E ratio of 31.2.", "pe_ratio", snap).verdict == "unverifiable"


# ----------------------------------------------------------------------
# Explicit signs
# ----------------------------------------------------------------------


def test_explicit_minus_sign_is_read():
    """ "-4.48% change" states its own sign; no verb is needed to infer it."""
    assert (
        _claim("The stock saw a -4.48% change over the past month.", "change_30d_pct").stated
        == -4.48
    )


def test_explicit_sign_verifies_against_a_negative_actual():
    assert (
        _verdicts("Volatility with a -2.99% change over the past month.")["change_30d_pct"]
        == "verified"
    )


def test_hyphen_inside_a_compound_word_is_not_a_sign():
    """ "30-day low of 302.25" must not parse as negative 302.25."""
    assert _claim("Trading near its 30-day low of 302.25.", "low_30d").stated == 302.25


def test_explicit_sign_overrides_a_misleading_verb():
    claim = _claim(
        "Momentum rose, but the 30-day change was -2.99% over the past month.", "change_30d_pct"
    )
    assert claim.stated == -2.99


def test_negative_currency_amount_parses():
    assert _claim("The current price of -5.0 is nonsense.", "price").stated == -5.0
