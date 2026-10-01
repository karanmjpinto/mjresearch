"""Market regime clustering on the space of return distributions.

Horvath, Issa and Muguruza, *Clustering Market Regimes Using the Wasserstein
Distance* (SSRN 3947905), implemented for daily single-name equity data.

    wasserstein  the algorithm — W1, the barycentre, and WK-means
    hmm          the hidden chain: forward, Viterbi, Baum-Welch, and the
                 transition matrix the clustering has no room for
    mmd          scoring a labelling that has no answer key
    synthetic    paths whose regimes are known, for the tests
    detect       one price series in, a scored labelling out

Read :mod:`.wasserstein` first: it says what the method is and, more usefully,
what it is not.
"""

from hedge_fund.regimes.detect import DEFAULT_H1, DEFAULT_H2, Analysis, HmmView, analyse
from hedge_fund.regimes.wasserstein import RegimeError

__all__ = ["DEFAULT_H1", "DEFAULT_H2", "Analysis", "HmmView", "RegimeError", "analyse"]
