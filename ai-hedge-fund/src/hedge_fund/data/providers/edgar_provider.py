"""SEC EDGAR provider — filings, peers by SIC, insider & institutional filing metadata.

Uses SEC's free public APIs (data.sec.gov, efts.sec.gov). No API key required,
but SEC mandates a descriptive User-Agent with contact info (env var SEC_USER_AGENT).
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import date, datetime
from typing import Any

import httpx

from hedge_fund.data.cache import DataCategory
from hedge_fund.data.models import (
    InsiderTransaction,
    InstitutionalHolder,
    PeerComparison,
    SECFiling,
)
from hedge_fund.data.providers.base import BaseProvider

logger = logging.getLogger(__name__)

# SEC requires a User-Agent with a descriptive name + email contact.
# See https://www.sec.gov/os/accessing-edgar-data
_DEFAULT_UA = "ai-hedge-fund/0.1 contact@example.com"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
_BROWSE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"

# SEC enforces ~10 req/sec. Keep a conservative min-interval between calls.
_MIN_INTERVAL_S = 0.12

# Form types we surface on the alt-data tab
_INTERESTING_FORMS = {
    "10-K",
    "10-Q",
    "8-K",
    "4",
    "13F-HR",
    "13F-HR/A",
    "SC 13G",
    "SC 13D",
    "DEF 14A",
}


class EdgarProvider(BaseProvider):
    """SEC EDGAR — filings + SIC-based peers + insider/institutional filing metadata.

    Priority 1 for SEC_FILINGS and PEERS (takes over from yfinance stub).
    Priority 3 for INSIDER/INSTITUTIONAL (yfinance has cleaner parsed data there).
    """

    name = "edgar"
    priority = 1
    categories = {
        DataCategory.SEC_FILINGS,
        DataCategory.PEERS,
    }

    # class-level cache for the ticker → CIK map (~3 MB, refreshed once per process)
    _ticker_map: dict[str, dict[str, Any]] | None = None
    _cik_to_meta: dict[str, dict[str, Any]] | None = None

    def __init__(self) -> None:
        self._ua = os.getenv("SEC_USER_AGENT", _DEFAULT_UA)
        self._last_call = 0.0
        self._client = httpx.Client(
            headers={
                "User-Agent": self._ua,
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=30.0,
        )

    def available(self) -> bool:
        # SEC APIs are public; always available as long as network is up.
        # The User-Agent requirement is enforced at call time.
        return True

    # --- BaseProvider interface ---------------------------------------

    def fetch(self, category: DataCategory, ticker: str, **kwargs: Any) -> Any:  # noqa: ARG002
        t = ticker.upper().strip()
        try:
            if category == DataCategory.SEC_FILINGS:
                return self._filings(t)
            if category == DataCategory.PEERS:
                return self._peers(t)
            if category == DataCategory.INSIDER:
                return self._insider_from_form4(t)
            if category == DataCategory.INSTITUTIONAL:
                return self._institutional_from_13f(t)
        except Exception as exc:
            logger.debug("EDGAR fetch(%s, %s) failed: %s", category.value, t, exc)
            return None
        return None

    # --- Rate-limited GET ---------------------------------------------

    def _throttle(self) -> None:
        delta = time.monotonic() - self._last_call
        if delta < _MIN_INTERVAL_S:
            time.sleep(_MIN_INTERVAL_S - delta)
        self._last_call = time.monotonic()

    def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        self._throttle()
        resp = self._client.get(url, **kwargs)
        resp.raise_for_status()
        return resp

    # --- Ticker / CIK lookups -----------------------------------------

    def _load_ticker_map(self) -> dict[str, dict[str, Any]]:
        if EdgarProvider._ticker_map is not None:
            return EdgarProvider._ticker_map
        try:
            resp = self._get(_TICKERS_URL)
            raw: dict[str, dict[str, Any]] = resp.json()
        except Exception as exc:
            logger.warning("EDGAR ticker map fetch failed: %s", exc)
            return {}
        # raw shape: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
        ticker_map: dict[str, dict[str, Any]] = {}
        cik_to_meta: dict[str, dict[str, Any]] = {}
        for entry in raw.values():
            t = str(entry.get("ticker", "")).upper()
            cik = str(entry.get("cik_str", "")).zfill(10)
            if t and cik:
                rec = {"cik": cik, "name": entry.get("title", "")}
                ticker_map[t] = rec
                cik_to_meta[cik] = {"ticker": t, "name": entry.get("title", "")}
        EdgarProvider._ticker_map = ticker_map
        EdgarProvider._cik_to_meta = cik_to_meta
        return ticker_map

    def _cik_for_ticker(self, ticker: str) -> str | None:
        return self._load_ticker_map().get(ticker, {}).get("cik")

    def _ticker_for_cik(self, cik: str) -> str | None:
        self._load_ticker_map()  # ensure populated
        meta = (EdgarProvider._cik_to_meta or {}).get(cik.zfill(10))
        return meta.get("ticker") if meta else None

    # --- Submissions (filings + SIC) ----------------------------------

    def _submissions(self, cik: str) -> dict[str, Any] | None:
        try:
            resp = self._get(_SUBMISSIONS_URL.format(cik=cik.zfill(10)))
            return resp.json()
        except Exception as exc:
            logger.debug("EDGAR submissions(%s) failed: %s", cik, exc)
            return None

    # --- Filings -------------------------------------------------------

    def _filings(self, ticker: str) -> list[SECFiling] | None:
        cik = self._cik_for_ticker(ticker)
        if not cik:
            return None
        sub = self._submissions(cik)
        if not sub:
            return None
        recent = sub.get("filings", {}).get("recent", {})
        forms: list[str] = recent.get("form", [])
        filed: list[str] = recent.get("filingDate", [])
        accepted: list[str] = recent.get("acceptanceDateTime", [])
        accession: list[str] = recent.get("accessionNumber", [])
        primary_docs: list[str] = recent.get("primaryDocument", [])
        descriptions: list[str] = recent.get("primaryDocDescription", [])

        out: list[SECFiling] = []
        for i, form in enumerate(forms):
            if form not in _INTERESTING_FORMS:
                continue
            acc = accession[i] if i < len(accession) else ""
            acc_nodash = acc.replace("-", "")
            doc = primary_docs[i] if i < len(primary_docs) else ""
            url = f"{_ARCHIVES}/{int(cik)}/{acc_nodash}/{doc}" if acc_nodash and doc else None
            out.append(
                SECFiling(
                    ticker=ticker,
                    form_type=form,
                    filed_date=_parse_date(filed[i] if i < len(filed) else None),
                    accepted_date=_parse_dt(accepted[i] if i < len(accepted) else None),
                    report_url=url,
                    description=(
                        descriptions[i] if i < len(descriptions) and descriptions[i] else None
                    ),
                    source="edgar",
                )
            )
            if len(out) >= 40:
                break
        return out

    # --- Peers via SIC -------------------------------------------------

    def _peers(self, ticker: str) -> PeerComparison | None:
        cik = self._cik_for_ticker(ticker)
        if not cik:
            return None
        sub = self._submissions(cik)
        if not sub:
            return None
        sic = str(sub.get("sic") or "")
        sic_desc = sub.get("sicDescription") or None
        if not sic:
            return PeerComparison(
                ticker=ticker,
                peers=[],
                sector=None,
                industry=sic_desc,
                metrics={},
                source="edgar",
            )

        # Fetch a wider candidate pool, then rank by market cap so we surface
        # real peers (large caps) instead of whichever small-cap filed a 10-K last week.
        candidates = self._search_peers_by_sic(sic, exclude_ticker=ticker, limit=40)
        metrics = self._peer_metrics(ticker, candidates)

        # Rank candidates by market cap descending; drop ones without a cap.
        ranked = sorted(
            (t for t in candidates if metrics.get(t, {}).get("market_cap")),
            key=lambda t: metrics[t]["market_cap"] or 0,
            reverse=True,
        )[:10]

        # Rebuild metrics restricted to the kept peers + self for smaller payload.
        kept_metrics = {ticker: metrics.get(ticker, {})}
        for t in ranked:
            kept_metrics[t] = metrics.get(t, {})

        return PeerComparison(
            ticker=ticker,
            peers=ranked,
            sector=None,  # EDGAR doesn't map SIC → GICS sector
            industry=sic_desc,
            metrics=kept_metrics,
            source="edgar",
        )

    def _search_peers_by_sic(self, sic: str, *, exclude_ticker: str, limit: int = 40) -> list[str]:
        """Find companies with the same SIC via EDGAR browse-edgar atom feed.

        This endpoint returns companies whose SIC classification matches (not
        just filing-text matches like the EFTS search-index). Response is an
        atom XML feed containing <cik> tags per entry.
        """
        try:
            resp = self._get(
                _BROWSE_URL,
                params={
                    "action": "getcompany",
                    "SIC": sic,
                    "type": "10-K",
                    "dateb": "",
                    "owner": "include",
                    "count": 100,
                    "output": "atom",
                },
            )
            text = resp.text
        except Exception as exc:
            logger.debug("EDGAR peer browse (sic=%s) failed: %s", sic, exc)
            return []

        # Atom feed contains <cik>0000320193</cik> inside each <entry>
        ciks = re.findall(r"<cik>\s*(\d+)\s*</cik>", text)
        seen: set[str] = set()
        out: list[str] = []
        for cik in ciks:
            t = self._ticker_for_cik(str(cik))
            if not t or t == exclude_ticker or t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= limit:
                break
        return out

    def _peer_metrics(
        self, ticker: str, peer_tickers: list[str]
    ) -> dict[str, dict[str, float | None]]:
        """Pull compact fundamentals for each ticker via yfinance (best-effort)."""
        try:
            import yfinance as yf  # local import to avoid hard dep at registration
        except ImportError:
            return {}

        out: dict[str, dict[str, float | None]] = {}
        for t in [ticker, *peer_tickers]:
            try:
                info = yf.Ticker(t).info
                out[t] = {
                    "pe_ratio": _safe_num(info.get("trailingPE")),
                    "forward_pe": _safe_num(info.get("forwardPE")),
                    "price_to_book": _safe_num(info.get("priceToBook")),
                    "profit_margin": _safe_num(info.get("profitMargins")),
                    "return_on_equity": _safe_num(info.get("returnOnEquity")),
                    "revenue_growth": _safe_num(info.get("revenueGrowth")),
                    "dividend_yield": _safe_num(info.get("dividendYield")),
                    "beta": _safe_num(info.get("beta")),
                    "market_cap": _safe_num(info.get("marketCap")),
                }
            except Exception as exc:
                logger.debug("yfinance metrics for %s failed: %s", t, exc)
                out[t] = {}
        return out

    # --- Insider (Form 4) metadata ------------------------------------

    def _insider_from_form4(self, ticker: str) -> list[InsiderTransaction] | None:
        """Surface recent Form 4 filings as InsiderTransaction rows.

        NOTE: Full Form 4 XML parsing (exact shares/price/role) is a large
        undertaking. This returns each Form 4 as a row with filer name and
        filing URL so the UI can link out. Higher-fidelity parsing is a
        future enhancement (Phase 5.5).
        """
        cik = self._cik_for_ticker(ticker)
        if not cik:
            return None
        sub = self._submissions(cik)
        if not sub:
            return None
        recent = sub.get("filings", {}).get("recent", {})
        forms: list[str] = recent.get("form", [])
        filed: list[str] = recent.get("filingDate", [])

        out: list[InsiderTransaction] = []
        for i, form in enumerate(forms):
            if form != "4":
                continue
            out.append(
                InsiderTransaction(
                    ticker=ticker,
                    name="(see filing)",
                    title=None,
                    transaction_type="Form 4 filing",
                    shares=0,
                    value=None,
                    date=_parse_date(filed[i] if i < len(filed) else None),
                    source="edgar",
                )
            )
            if len(out) >= 25:
                break
        return out or None

    # --- Institutional (13F) metadata ---------------------------------

    def _institutional_from_13f(self, ticker: str) -> list[InstitutionalHolder] | None:
        """Find 13F-HR filings mentioning this issuer via EDGAR full-text search.

        Returns a flat list of filer names + dates. Share-count detail requires
        XBRL/XML parsing (deferred to Phase 5.5 13F-delta work).
        """
        cik = self._cik_for_ticker(ticker)
        if not cik:
            return None
        try:
            resp = self._get(
                _EFTS_URL,
                params={
                    "q": ticker,
                    "forms": "13F-HR",
                    "dateRange": "custom",
                    "startdt": "2024-01-01",
                    "enddt": datetime.now().strftime("%Y-%m-%d"),
                },
            )
            data = resp.json()
        except Exception as exc:
            logger.debug("EDGAR 13F search (%s) failed: %s", ticker, exc)
            return None

        hits = (data.get("hits") or {}).get("hits") or []
        out: list[InstitutionalHolder] = []
        for h in hits[:25]:
            src = h.get("_source") or {}
            name = (src.get("display_names") or ["(unknown filer)"])[0]
            filed_at = src.get("file_date")
            out.append(
                InstitutionalHolder(
                    ticker=ticker,
                    holder=str(name).split(" (CIK")[0],
                    shares=0,
                    value=None,
                    pct_held=None,
                    date_reported=_parse_date(filed_at),
                    source="edgar",
                )
            )
        return out or None


# --- helpers ---------------------------------------------------------------


def _parse_date(s: Any) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_dt(s: Any) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _safe_num(v: Any) -> float | None:
    import math

    try:
        if v is None:
            return None
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None
