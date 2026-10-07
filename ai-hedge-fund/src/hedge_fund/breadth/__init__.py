"""Market breadth, and whether it is diverging from the index.

The one screen in this project that is about the market rather than about a
company. It lives apart from :mod:`hedge_fund.macro` on purpose: macro asks
what the economy did to a company, breadth asks what the rest of the index is
doing while the index itself makes highs.
"""

from hedge_fund.breadth.divergence import (
    DEFAULT_FLOOR,
    DEFAULT_NEAR,
    GAP_DAYS,
    HORIZONS,
    analyse,
)
from hedge_fund.breadth.series import Breadth, from_closes
from hedge_fund.breadth.store import (
    REFRESH,
    BreadthDataMissing,
    BreadthUniverseInvalid,
    StoredBreadth,
    available,
    read,
    write,
)

__all__ = [
    "DEFAULT_FLOOR",
    "DEFAULT_NEAR",
    "GAP_DAYS",
    "HORIZONS",
    "Breadth",
    "BreadthDataMissing",
    "BreadthUniverseInvalid",
    "REFRESH",
    "StoredBreadth",
    "analyse",
    "available",
    "from_closes",
    "read",
    "write",
]
