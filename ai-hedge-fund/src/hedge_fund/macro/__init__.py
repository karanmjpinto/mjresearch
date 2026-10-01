"""Where a return series sits against US growth and inflation news.

Two modules. :mod:`news` reads the committed quarterly news metrics that
``scripts/refresh_macro_news.py`` builds; :mod:`sensitivity` turns any return
series into the pair of partial correlations that place it on the map.

The map is descriptive and backward-looking. A point says how a series has
covaried with macro news across half a century, not what it will do next, and
half a century of overlapping windows is fewer independent observations than
the point count suggests — every figure here carries the standard error that
says so.
"""

from hedge_fund.macro import news, sensitivity
from hedge_fund.macro.news import MacroDataMissing

__all__ = ["MacroDataMissing", "news", "sensitivity"]
