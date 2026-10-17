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


# ----------------------------------------------------------------------
# Alias boundaries
# ----------------------------------------------------------------------


def test_pe_alias_does_not_match_inside_sharpe():
    """'sharpe ratio' contains 'pe ratio'. A Sharpe value is not a P/E."""
    snap = {"fundamentals": {"pe_ratio": 26.92}, "computed": {"sharpe_ratio": -0.094}}
    claims = extract_claims("The stock has a negative Sharpe ratio (-0.094).", snap)
    assert all(c.metric != "pe_ratio" for c in claims), "Sharpe value read as a P/E"


def test_sharpe_claim_verifies_against_computed_facts():
    snap = {"computed": {"sharpe_ratio": -0.094}}
    assert _verdicts("A negative Sharpe ratio (-0.094) is unattractive.", snap) == {
        "sharpe_ratio": "verified"
    }


def test_sortino_claim_verifies():
    snap = {"computed": {"sortino_ratio": -0.146}}
    assert _verdicts("Sortino ratio of -0.146.", snap)["sortino_ratio"] == "verified"


def test_wrong_sharpe_is_caught():
    snap = {"computed": {"sharpe_ratio": -0.094}}
    assert _verdicts("A Sharpe ratio of 1.8 is excellent.", snap)["sharpe_ratio"] == "mismatch"


@pytest.mark.parametrize(
    "text,absent",
    [
        # "unive*rsi*ty" contains rsi; "*peg*ged" contains peg;
        # "shar*pe ratio*" contains "pe ratio".
        ("A university study covering 42 companies.", "rsi_14"),
        ("The currency is pegged at 42 to the dollar.", "peg_ratio"),
        ("Sharpe ratio of 42 across the book.", "pe_ratio"),
    ],
)
def test_aliases_do_not_match_mid_word(text, absent):
    snap = {
        "technicals": {"rsi_14": 47.3},
        "fundamentals": {"peg_ratio": 2.0, "pe_ratio": 26.9},
        "computed": {"sharpe_ratio": 42.0},
    }
    assert all(c.metric != absent for c in extract_claims(text, snap))


def test_real_bear_case_verifies_cleanly():
    """The live run that exposed the boundary bug, as a regression."""
    snap = {
        "fundamentals": {"pe_ratio": 26.92479, "peg_ratio": 1.5728, "price_to_book": 8.113825},
        "computed": {"sharpe_ratio": -0.094, "sortino_ratio": -0.146},
    }
    text = (
        "The company's fundamentals show a reasonable valuation multiple (PE ratio of 26.9), "
        "price-to-book at 8.1, and peg ratio of 1.57. Momentum has declined, with a negative "
        "Sharpe ratio (-0.094) and Sortino ratio (-0.146)."
    )
    claims = extract_claims(text, snap)
    assert claims, "expected claims to be found"
    assert [c for c in claims if c.verdict == "mismatch"] == []


# ----------------------------------------------------------------------
# Binding a number to the wrong metric. Every "false alarm" case below is prose
# a live committee wrote on a frozen fixture, which the verifier reported as a
# contradiction when the prose was right. Each is paired with the real error it
# must still catch, so the fix cannot be a quiet loosening.

BIND = {
    "price": {"current": 17.04, "change_30d_pct": -16.4},
    "fundamentals": {
        "pe_ratio": 7.3133,
        "peg_ratio": 3.9244,
        "price_to_book": 0.7231,
        "dividend_yield": 4.91,
        "52w_high": 344.57,
    },
    "technicals": {"rsi_14": 35.56, "sma_200": 17.2},
}


def test_a_number_on_the_next_line_belongs_to_the_next_statement():
    text = "Price near 52-week high with limited downside buffer\nElevated RSI (35.5) signals risk"
    claims = extract_claims(text, BIND)
    assert [c.metric for c in claims] == ["rsi_14"]
    assert claims[0].verdict == "verified"


def test_a_wrong_52_week_high_in_its_own_statement_is_still_caught():
    claim = _claim("The 52-week high of $6 leaves little buffer", "week52_high", BIND)
    assert claim.verdict == "mismatch"


def test_a_number_in_the_next_sentence_belongs_to_the_next_sentence():
    text = "It offers a high dividend yield. The low price-to-book ratio (0.72) adds support."
    claims = extract_claims(text, BIND)
    assert {c.metric: c.verdict for c in claims} == {"price_to_book": "verified"}


def test_a_multiple_is_not_the_share_price():
    """ "Trading at 7.3x P/E" — the price took 7.3 and the P/E took the industry's 25."""
    text = "Trading at 7.3x P/E vs industry average of ~25x, and 0.72x price-to-book"
    claims = {c.metric: c for c in extract_claims(text, BIND)}
    assert "price" not in claims
    assert claims["pe_ratio"].stated == 7.3 and claims["pe_ratio"].verdict == "verified"


def test_a_wrong_price_and_a_wrong_multiple_are_still_caught():
    assert _claim("Trading at $7.30 after the sell-off", "price", BIND).verdict == "mismatch"
    assert _claim("On a P/E of 25x the stock is dear", "pe_ratio", BIND).verdict == "mismatch"


def test_a_peer_figure_is_unverifiable_not_a_contradiction():
    text = "PEG ratio of 3.92 is rich. Sector peers trade at higher PEG ratios (e.g., 1.5-2.0)"
    claims = [c for c in extract_claims(text, BIND) if c.metric == "peg_ratio"]
    by_value = {c.stated: c for c in claims}
    assert by_value[3.92].verdict == "verified"
    assert by_value[1.5].verdict == "unverifiable"
    assert "peers" in by_value[1.5].note


def test_a_moving_average_before_a_metric_is_not_a_peer_average():
    """ "average" before the metric name is half of "moving average", not a comparison."""
    snap = {"technicals": {"sma_50": 40.97, "sma_200": 43.79}}
    text = "Below its 50-day moving average of 40.97 and 200-day moving average of 43.79"
    assert _verdicts(text, snap) == {"sma_50": "verified", "sma_200": "verified"}


def test_a_bound_is_checked_as_a_bound():
    assert _claim("Weak technicals (RSI below 40)", "rsi_14", BIND).verdict == "verified"
    assert _claim("Weak technicals (RSI below 40)", "rsi_14", BIND).note == "read as an upper bound"
    assert _claim("RSI above 30 shows no capitulation", "rsi_14", BIND).verdict == "verified"


def test_a_false_bound_is_still_caught():
    assert _claim("Deeply oversold (RSI below 30)", "rsi_14", BIND).verdict == "mismatch"
    assert _claim("Overbought with RSI above 70", "rsi_14", BIND).verdict == "mismatch"


def test_a_bound_word_before_the_metric_does_not_make_its_value_a_bound():
    """ "Price below 200-day SMA ($17.20)" states the SMA; it does not bound it."""
    claim = _claim("Price below 200-day SMA ($17.20)", "sma_200", BIND)
    assert claim.verdict == "verified" and claim.note is None
    assert _claim("Price below 200-day SMA ($19.90)", "sma_200", BIND).verdict == "mismatch"


def test_a_price_range_is_not_a_30_day_change():
    text = "High volatility with 30-day range (95.98-118.20) persists"
    assert "change_30d_pct" not in _verdicts(text, BIND)


def test_a_wrong_30_day_change_with_its_percent_is_still_caught():
    assert _claim("Fell 4% over the past month", "change_30d_pct", BIND).verdict == "mismatch"
    assert _claim("Fell 16.4% over the past month", "change_30d_pct", BIND).verdict == "verified"


def test_a_window_length_is_not_a_value():
    text = "Given current price action over 30 days, caution is warranted"
    assert "price" not in _verdicts(text, BIND)
    assert _claim("The 14-day RSI of 35.6 is weak", "rsi_14", BIND).stated == 35.6


def test_an_indicator_reading_is_not_a_momentum_percentage():
    snap = {"computed": {"momentum_pct": -8.88}, "technicals": {"rsi_14": 20.84}}
    text = "Technicals show bearish momentum (RSI=20.84)"
    assert _verdicts(text, snap) == {"rsi_14": "verified"}
    assert _claim("Negative price momentum (-3.1%)", "momentum_pct", snap).verdict == "mismatch"


def test_a_number_past_the_search_window_is_not_read_in_half():
    """The window used to be a slice, so "(69.3)" at its edge was read as 6."""
    text = "Price near 52-week high with limited downside buffer and elevated RSI (69.3)"
    claims = extract_claims(text, {"fundamentals": {"52w_high": 344.57}})
    assert all(c.stated != 6.0 for c in claims)


def test_a_peer_figure_before_a_comma_does_not_taint_the_next_metric():
    snap = {"fundamentals": {"pe_ratio": 7.64, "forward_pe": 10.188}}
    text = "A P/E ratio (7.64x) significantly below sector average (~15x), forward PE (10.19x)"
    claims = {c.metric: c for c in extract_claims(text, snap)}
    assert claims["pe_ratio"].stated == 7.64 and claims["pe_ratio"].verdict == "verified"
    assert claims["forward_pe"].stated == 10.19 and claims["forward_pe"].verdict == "verified"
    wrong = "A P/E ratio (7.64x) below sector average (~15x), forward PE (14.0x)"
    assert _claim(wrong, "forward_pe", snap).verdict == "mismatch"


def test_a_number_goes_to_the_metric_named_nearest_to_it():
    snap = {"price": {"low_30d": 88.65}, "technicals": {"rsi_14": 20.84}}
    text = "The price is near a 30-day low with oversold technicals (RSI=20.84)"
    assert _verdicts(text, snap) == {"rsi_14": "verified"}
    assert _claim("Near its 30-day low ($70.10)", "low_30d", snap).verdict == "mismatch"


# --- Checking prose against the plan's own computed fields ---------------

from hedge_fund.agents.verifier import specs_for_facts  # noqa: E402

PLAN_FACTS = {"recent_volatility_pct": 26.73, "volatility_ratio": 0.868, "regime": "normal"}


def test_a_computed_field_quoted_correctly_is_verified_not_ignored():
    """Observed on the eval: a correct thesis reported as citing nothing."""
    text = "Recent volatility of 26.73% sits below its baseline."
    v = verify_analysis(
        {"investment_thesis": text}, {"computed": PLAN_FACTS}, specs_for_facts(PLAN_FACTS)
    )
    assert v["status"] == "clean" and v["verified"] == 1


def test_a_computed_field_quoted_wrongly_is_a_mismatch():
    text = "Recent volatility of 41.5% is elevated."
    v = verify_analysis(
        {"investment_thesis": text}, {"computed": PLAN_FACTS}, specs_for_facts(PLAN_FACTS)
    )
    assert v["status"] == "mismatch"


def test_fact_specs_skip_text_and_fields_a_hand_written_spec_owns():
    names = {s.name for s in specs_for_facts({**PLAN_FACTS, "rsi_14": 44.0, "flag": True})}
    assert names == {"recent_volatility_pct", "volatility_ratio"}


def test_a_number_belongs_to_the_name_before_it_not_a_later_name_reading_back():
    """'PEG ratio (2.67) ... trading at a premium': 2.67 is not the share price."""
    text = "The PEG ratio (2.67) suggests the stock is trading at a premium."
    claims = {c.metric: c for c in extract_claims(text, BIND)}
    assert "price" not in claims


def test_one_word_fields_and_unmarked_percentages_are_not_read_as_facts():
    facts = {"high": 340.0, "recent_volatility_pct": 26.73, "volatility_ratio": 0.868}
    text = "The P/E is very high at 45.8. The recent volatility ratio (0.868) is low."
    v = verify_analysis({"investment_thesis": text}, {"computed": facts}, specs_for_facts(facts))
    assert v["mismatched"] == 0


def test_a_figure_said_twice_still_owns_its_number():
    text = (
        "PEG ratio (2.67) is high. A PEG ratio (2.67) suggests the stock is trading at a premium."
    )
    claims = extract_claims(text, BIND)
    assert not [c for c in claims if c.metric == "price"]


def test_a_quoted_field_name_is_read_as_the_metric():
    """Observed: "pe_ratio=38.68714" reported as citing nothing."""
    assert _claim("Valuation is stretched (pe_ratio=7.3).", "pe_ratio", BIND).verdict == "verified"
