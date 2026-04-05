"""Nordic market helpers — validation and currency context for .ST/.CO/.HE tickers."""

from __future__ import annotations

NORDIC_SUFFIXES = {
    ".ST": {"exchange": "Stockholm (OMX)", "currency": "SEK", "country": "Sweden"},
    ".CO": {"exchange": "Copenhagen (OMX)", "currency": "DKK", "country": "Denmark"},
    ".HE": {"exchange": "Helsinki (OMX)", "currency": "EUR", "country": "Finland"},
}


def is_nordic_ticker(ticker: str) -> bool:
    return any(ticker.upper().endswith(s) for s in NORDIC_SUFFIXES)


def get_nordic_context(ticker: str) -> dict | None:
    """Return exchange/currency context for a Nordic ticker."""
    upper = ticker.upper()
    for suffix, ctx in NORDIC_SUFFIXES.items():
        if upper.endswith(suffix):
            return {**ctx, "ticker": ticker}
    return None


def validate_nordic_ticker(ticker: str) -> bool:
    """Check if a Nordic ticker is likely valid (basic heuristic)."""
    if not is_nordic_ticker(ticker):
        return False
    base = ticker.rsplit(".", 1)[0]
    return len(base) >= 2 and base.replace("-", "").isalpha()
