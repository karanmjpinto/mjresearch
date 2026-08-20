"""Enhanced yfinance provider — covers 10 data categories with no API key."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd
import yfinance as yf

from hedge_fund.data.cache import DataCategory
from hedge_fund.data.technicals_compute import compute_technicals_from_ohlcv
from hedge_fund.data.models import (
    AnalystRating,
    EarningsInfo,
    InsiderTransaction,
    InstitutionalHolder,
    OptionsChain,
    PeerComparison,
)
from hedge_fund.data.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class YFinanceEnhancedProvider(BaseProvider):
    name = "yfinance_enhanced"
    priority = 1
    categories = {
        DataCategory.PRICE,
        DataCategory.FUNDAMENTALS,
        DataCategory.TECHNICALS,
        DataCategory.EARNINGS,
        DataCategory.ANALYST,
        DataCategory.INSIDER,
        DataCategory.INSTITUTIONAL,
        DataCategory.OPTIONS,
        DataCategory.NEWS,
        DataCategory.PEERS,
    }

    def available(self) -> bool:
        return True  # yfinance needs no API key

    def fetch(self, category: DataCategory, ticker: str, **kwargs: Any) -> Any:
        dispatch = {
            DataCategory.PRICE: self._price,
            DataCategory.FUNDAMENTALS: self._fundamentals,
            DataCategory.TECHNICALS: self._technicals,
            DataCategory.EARNINGS: self._earnings,
            DataCategory.ANALYST: self._analyst,
            DataCategory.INSIDER: self._insider,
            DataCategory.INSTITUTIONAL: self._institutional,
            DataCategory.OPTIONS: self._options,
            DataCategory.NEWS: self._news,
            DataCategory.PEERS: self._peers,
        }
        handler = dispatch.get(category)
        if handler is None:
            return None
        return handler(ticker, **kwargs)

    # ------------------------------------------------------------------
    # Price
    # ------------------------------------------------------------------

    def _price(self, ticker: str, **kwargs: Any) -> pd.DataFrame | None:
        days = int(kwargs.get("days", 365))
        interval = kwargs.get("interval", "1d")
        t = yf.Ticker(ticker)
        end: date = kwargs.get("end_date") or date.today()
        start = end - timedelta(days=days)
        # yfinance end date is exclusive for daily bars
        df = t.history(start=start, end=end + timedelta(days=1), interval=interval)
        if df.empty:
            return None
        df.columns = [c.lower() for c in df.columns]
        return df

    # ------------------------------------------------------------------
    # Fundamentals
    # ------------------------------------------------------------------

    def _fundamentals(self, ticker: str, **kwargs: Any) -> dict | None:
        t = yf.Ticker(ticker)
        info = t.info
        if not info or info.get("regularMarketPrice") is None:
            return None

        # 52w high/low: info dict first, fast_info as fallback
        _52w_high = info.get("fiftyTwoWeekHigh")
        _52w_low = info.get("fiftyTwoWeekLow")
        if _52w_high is None or _52w_low is None:
            try:
                fi = t.fast_info
                _52w_high = (
                    _52w_high if _52w_high is not None else getattr(fi, "fifty_two_week_high", None)
                )
                _52w_low = (
                    _52w_low if _52w_low is not None else getattr(fi, "fifty_two_week_low", None)
                )
            except Exception:
                pass

        result = {
            "ticker": ticker,
            "name": info.get("longName", ticker),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "peg_ratio": info.get("pegRatio"),
            "price_to_book": info.get("priceToBook"),
            "dividend_yield": info.get("dividendYield"),
            "beta": info.get("beta"),
            "52w_high": _safe_float(_52w_high),
            "52w_low": _safe_float(_52w_low),
            "avg_volume": info.get("averageVolume"),
            "currency": info.get("currency", "USD"),
            "exchange": info.get("exchange"),
            "source": "yfinance",
        }

        # Add financial statements summary
        try:
            bs = t.balance_sheet
            inc = t.income_stmt
            cf = t.cashflow
            if not bs.empty:
                latest = bs.iloc[:, 0]
                result["total_assets"] = _safe_float(latest.get("Total Assets"))
                result["total_debt"] = _safe_float(latest.get("Total Debt"))
                result["total_equity"] = _safe_float(
                    latest.get("Stockholders Equity")
                    or latest.get("Total Equity Gross Minority Interest")
                )
            if not inc.empty:
                latest = inc.iloc[:, 0]
                # Try multiple key names — yfinance column names vary by version/region
                result["revenue"] = _safe_float(
                    latest.get("Total Revenue") or latest.get("Revenue")
                )
                result["net_income"] = _safe_float(
                    latest.get("Net Income")
                    or latest.get("Net Income From Continuing Operations")
                    or latest.get("Net Income Common Stockholders")
                )
                result["ebitda"] = _safe_float(
                    latest.get("EBITDA") or latest.get("Normalized EBITDA")
                )
            if not cf.empty:
                latest = cf.iloc[:, 0]
                result["free_cash_flow"] = _safe_float(latest.get("Free Cash Flow"))
                result["operating_cash_flow"] = _safe_float(latest.get("Operating Cash Flow"))
        except Exception:
            pass

        return result

    # ------------------------------------------------------------------
    # Technicals (computed from price)
    # ------------------------------------------------------------------

    def _technicals(self, ticker: str, **kwargs: Any) -> dict | None:
        df = self._price(ticker, days=365)
        return compute_technicals_from_ohlcv(df, ticker, source="yfinance")

    # ------------------------------------------------------------------
    # Earnings
    # ------------------------------------------------------------------

    def _earnings(self, ticker: str, **kwargs: Any) -> EarningsInfo | None:
        t = yf.Ticker(ticker)
        try:
            dates_df = t.earnings_dates
            quarterly = t.quarterly_earnings

            earnings_dates = []
            if dates_df is not None and not dates_df.empty:
                for idx, row in dates_df.head(8).iterrows():
                    earnings_dates.append(
                        {
                            "date": str(idx.date()) if hasattr(idx, "date") else str(idx),
                            "eps_estimate": _safe_float(row.get("EPS Estimate")),
                            "reported_eps": _safe_float(row.get("Reported EPS")),
                            "surprise_pct": _safe_float(row.get("Surprise(%)")),
                        }
                    )

            quarterly_list = []
            if quarterly is not None and not quarterly.empty:
                for idx, row in quarterly.iterrows():
                    quarterly_list.append(
                        {
                            "quarter": str(idx),
                            "revenue": _safe_float(row.get("Revenue")),
                            "earnings": _safe_float(row.get("Earnings")),
                        }
                    )

            # Next earnings date
            next_date = None
            if earnings_dates:
                from datetime import date as dt_date

                today = dt_date.today()
                for ed in earnings_dates:
                    try:
                        d = dt_date.fromisoformat(ed["date"])
                        if d >= today:
                            next_date = d
                            break
                    except (ValueError, TypeError):
                        pass

            return EarningsInfo(
                ticker=ticker,
                next_earnings_date=next_date,
                earnings_dates=earnings_dates,
                quarterly_earnings=quarterly_list,
                source="yfinance",
            )
        except Exception as e:
            logger.warning("yfinance earnings error for %s: %s", ticker, e)
            return None

    # ------------------------------------------------------------------
    # Analyst
    # ------------------------------------------------------------------

    def _analyst(self, ticker: str, **kwargs: Any) -> AnalystRating | None:
        t = yf.Ticker(ticker)
        info = t.info
        try:
            recs = t.recommendations
            rec_history = []
            if recs is not None and not recs.empty:
                for idx, row in recs.tail(10).iterrows():
                    rec_history.append(
                        {
                            "date": str(idx.date()) if hasattr(idx, "date") else str(idx),
                            "firm": row.get("Firm", ""),
                            "grade": row.get("To Grade", ""),
                            "action": row.get("Action", ""),
                        }
                    )

            target_mean = info.get("targetMeanPrice")
            current = info.get("currentPrice") or info.get("regularMarketPrice")
            upside = None
            if target_mean and current and current > 0:
                upside = round((target_mean - current) / current * 100, 1)

            return AnalystRating(
                ticker=ticker,
                target_mean=target_mean,
                target_median=info.get("targetMedianPrice"),
                target_high=info.get("targetHighPrice"),
                target_low=info.get("targetLowPrice"),
                current_price=current,
                upside_pct=upside,
                num_analysts=info.get("numberOfAnalystOpinions"),
                recommendation=info.get("recommendationKey"),
                recommendation_history=rec_history,
                source="yfinance",
            )
        except Exception as e:
            logger.warning("yfinance analyst error for %s: %s", ticker, e)
            return None

    # ------------------------------------------------------------------
    # Insider transactions
    # ------------------------------------------------------------------

    def _insider(self, ticker: str, **kwargs: Any) -> list[InsiderTransaction] | None:
        t = yf.Ticker(ticker)
        try:
            txns = t.insider_transactions
            if txns is None or txns.empty:
                return []

            results = []
            for _, row in txns.head(20).iterrows():
                results.append(
                    InsiderTransaction(
                        ticker=ticker,
                        name=str(row.get("Insider", "Unknown")),
                        title=str(row.get("Position", ""))
                        if pd.notna(row.get("Position"))
                        else None,
                        transaction_type=str(row.get("Transaction", "Unknown")),
                        shares=int(row.get("Shares", 0)) if pd.notna(row.get("Shares")) else 0,
                        value=_safe_float(row.get("Value")),
                        date=_safe_date(row.get("Start Date")),
                        source="yfinance",
                    )
                )
            return results
        except Exception as e:
            logger.warning("yfinance insider error for %s: %s", ticker, e)
            return None

    # ------------------------------------------------------------------
    # Institutional holders
    # ------------------------------------------------------------------

    def _institutional(self, ticker: str, **kwargs: Any) -> list[InstitutionalHolder] | None:
        t = yf.Ticker(ticker)
        try:
            holders = t.institutional_holders
            if holders is None or holders.empty:
                return []

            results = []
            for _, row in holders.head(20).iterrows():
                results.append(
                    InstitutionalHolder(
                        ticker=ticker,
                        holder=str(row.get("Holder", "Unknown")),
                        shares=int(row.get("Shares", 0)) if pd.notna(row.get("Shares")) else 0,
                        value=_safe_float(row.get("Value")),
                        pct_held=_safe_float(row.get("% Out")),
                        date_reported=_safe_date(row.get("Date Reported")),
                        source="yfinance",
                    )
                )
            return results
        except Exception as e:
            logger.warning("yfinance institutional error for %s: %s", ticker, e)
            return None

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------

    def _options(self, ticker: str, **kwargs: Any) -> OptionsChain | None:
        t = yf.Ticker(ticker)
        try:
            expirations = list(t.options) if t.options else []
            if not expirations:
                return OptionsChain(ticker=ticker, source="yfinance")

            # Get nearest expiration
            chain = t.option_chain(expirations[0])
            calls = chain.calls.head(20).to_dict(orient="records") if not chain.calls.empty else []
            puts = chain.puts.head(20).to_dict(orient="records") if not chain.puts.empty else []

            # Clean NaN values
            calls = _clean_records(calls)
            puts = _clean_records(puts)

            return OptionsChain(
                ticker=ticker,
                expirations=expirations[:6],
                calls=calls,
                puts=puts,
                source="yfinance",
            )
        except Exception as e:
            logger.warning("yfinance options error for %s: %s", ticker, e)
            return None

    # ------------------------------------------------------------------
    # News
    # ------------------------------------------------------------------

    def _news(self, ticker: str, **kwargs: Any) -> list[dict] | None:
        t = yf.Ticker(ticker)
        try:
            news = t.news
            if not news:
                return []
            results = []
            for item in news[:10]:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "publisher": item.get("publisher", ""),
                        "link": item.get("link", ""),
                        "published": item.get("providerPublishTime", ""),
                        "type": item.get("type", ""),
                        "source": "yfinance",
                    }
                )
            return results
        except Exception as e:
            logger.warning("yfinance news error for %s: %s", ticker, e)
            return None

    # ------------------------------------------------------------------
    # Peers
    # ------------------------------------------------------------------

    def _peers(self, ticker: str, **kwargs: Any) -> PeerComparison | None:
        t = yf.Ticker(ticker)
        info = t.info
        sector = info.get("sector")
        industry = info.get("industry")

        if not sector:
            return None

        return PeerComparison(
            ticker=ticker,
            sector=sector,
            industry=industry,
            source="yfinance",
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _safe_float(val: Any) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_round(val: Any, decimals: int = 2) -> float | None:
    f = _safe_float(val)
    return round(f, decimals) if f is not None else None


def _safe_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    if hasattr(val, "date"):
        return val.date()
    try:
        return date.fromisoformat(str(val)[:10])
    except (ValueError, TypeError):
        return None


def _clean_records(records: list[dict]) -> list[dict]:
    """Replace NaN values with None in a list of dicts."""
    cleaned = []
    for rec in records:
        cleaned.append(
            {k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in rec.items()}
        )
    return cleaned
