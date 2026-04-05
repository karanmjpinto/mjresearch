"""BIST (Borsa Istanbul) data via borsapy, normalized to OpenBB conventions."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)

# BIST tickers on Yahoo Finance end with .IS
BIST_SUFFIX = ".IS"


def is_bist_ticker(ticker: str) -> bool:
    return ticker.upper().endswith(BIST_SUFFIX)


def strip_bist_suffix(ticker: str) -> str:
    if ticker.upper().endswith(BIST_SUFFIX):
        return ticker[: -len(BIST_SUFFIX)]
    return ticker


def get_bist_price(
    ticker: str,
    start: date,
    end: date,
) -> pd.DataFrame | None:
    """Fetch BIST price data via borsapy. Returns None if borsapy unavailable."""
    try:
        from borsapy.borsapy import BorsaIstanbul

        bist = BorsaIstanbul()
        clean_ticker = strip_bist_suffix(ticker)
        df = bist.get_stock_data(clean_ticker, start.isoformat(), end.isoformat())

        if df is None or df.empty:
            return None

        # Normalize column names to match OpenBB convention
        col_map = {
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")

        return df

    except ImportError:
        logger.debug("borsapy not installed — BIST data will fall back to yfinance")
        return None
    except Exception as e:
        logger.warning("borsapy error for %s: %s", ticker, e)
        return None
