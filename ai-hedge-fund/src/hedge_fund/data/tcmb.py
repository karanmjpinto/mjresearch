"""TCMB EVDS (Turkish Central Bank Electronic Data Delivery System)."""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

EVDS_BASE_URL = "https://evds2.tcmb.gov.tr/service/evds"

# Common EVDS series IDs
SERIES = {
    "policy_rate": "TP.PY.PO1",
    "cpi_annual": "TP.FG.J0",
    "usdtry": "TP.DK.USD.S.YTL",
    "eurtry": "TP.DK.EUR.S.YTL",
    "reserves_gross": "TP.AB.B1",
}


def get_evds_data(
    series_id: str,
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    """Fetch data from TCMB EVDS API. Requires TCMB_EVDS_KEY env var."""
    api_key = os.environ.get("TCMB_EVDS_KEY")
    if not api_key:
        logger.warning("TCMB_EVDS_KEY not set — returning empty DataFrame")
        return pd.DataFrame()

    if end is None:
        end = date.today()
    if start is None:
        start = end - timedelta(days=365 * 2)

    params = {
        "series": series_id,
        "startDate": start.strftime("%d-%m-%Y"),
        "endDate": end.strftime("%d-%m-%Y"),
        "type": "json",
        "key": api_key,
    }

    try:
        resp = httpx.get(EVDS_BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if "items" not in data:
            return pd.DataFrame()

        df = pd.DataFrame(data["items"])
        if "Tarih" in df.columns:
            df["date"] = pd.to_datetime(df["Tarih"], format="%d-%m-%Y")
            df = df.set_index("date")
            df = df.drop(columns=["Tarih"], errors="ignore")

        # Convert numeric columns
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    except Exception as e:
        logger.error("EVDS error for %s: %s", series_id, e)
        return pd.DataFrame()


def get_turkey_macro_snapshot() -> dict:
    """Get a quick snapshot of Turkish macro indicators."""
    snapshot = {}
    for name, sid in SERIES.items():
        df = get_evds_data(sid)
        if not df.empty:
            last_col = [c for c in df.columns if c != "YEARWEEK"]
            if last_col:
                val = df[last_col[0]].dropna()
                if not val.empty:
                    snapshot[name] = {
                        "value": float(val.iloc[-1]),
                        "date": str(val.index[-1].date()),
                        "series_id": sid,
                    }
    return snapshot
