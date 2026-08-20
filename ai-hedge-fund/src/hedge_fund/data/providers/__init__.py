"""Auto-register all data providers."""

from hedge_fund.data.providers.base import BaseProvider

# Import providers so they self-register via BaseProvider.__init_subclass__
from hedge_fund.data.providers import openbb_provider  # noqa: F401
from hedge_fund.data.providers import yfinance_enhanced  # noqa: F401

try:
    from hedge_fund.data.providers import edgar_provider  # noqa: F401
except ImportError:
    pass

try:
    from hedge_fund.data.providers import pandas_datareader_provider  # noqa: F401
except ImportError:
    pass

try:
    from hedge_fund.data.providers import finnhub_provider  # noqa: F401
except ImportError:
    pass

try:
    from hedge_fund.data.providers import twelvedata_provider  # noqa: F401
except ImportError:
    pass

try:
    from hedge_fund.data.providers import alpha_vantage_provider  # noqa: F401
except ImportError:
    pass

try:
    from hedge_fund.data.providers import financial_datasets_provider  # noqa: F401
except ImportError:
    pass

__all__ = ["BaseProvider"]
