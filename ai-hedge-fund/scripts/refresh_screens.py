"""Recompute the cached screens.

Run from the repo root:

    uv run python scripts/refresh_screens.py                    # both screens, each
                                                                # on the universe it
                                                                # is written for
    uv run python scripts/refresh_screens.py --universe sp400    # mid-caps
    uv run python scripts/refresh_screens.py --screen yartseva --max 120
    uv run python scripts/refresh_screens.py --fill              # retry what failed

Universes: sp500, sp400, sp600. With no --universe, each screen is refreshed on
its own default — the multi-bagger screen on the SmallCap 600, because its
market-cap ceiling means it cannot pass a single S&P 500 name.

Concurrency is the point. Each name costs a few seconds of waiting on
yfinance, almost none of it CPU, so the work is embarrassingly parallel and
running it in sequence is the difference between seven minutes and an hour.

The worker count is deliberately modest. This is an unauthenticated public
endpoint being asked five hundred questions, and the failure mode of pushing
harder is not a slow run, it is rate limiting that returns empty frames — which
this screen would faithfully record as a company with no financials. Slower and
correct beats faster and quietly wrong.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from hedge_fund.api.routes.screeners import DEFAULT_UNIVERSE_FOR as api_defaults
from hedge_fund.data.universes import load_universe
from hedge_fund.screeners import cache
from hedge_fund.screeners.bolton_contrarian import run_bolton_contrarian_for_ticker
from hedge_fund.screeners.acquisition_compounder import (
    run_acquisition_compounder_for_ticker,
)
from hedge_fund.screeners.yartseva import run_yartseva_for_ticker

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("refresh")

RUNNERS = {
    "yartseva": run_yartseva_for_ticker,
    "acquisition-compounder": run_acquisition_compounder_for_ticker,
    "bolton-contrarian": run_bolton_contrarian_for_ticker,
}

#: Imported from the API so the script and the page it feeds cannot drift.
#: A screen refreshed on one universe and read back from another shows
#: "nothing computed yet" with a cache sitting right there on disk.
DEFAULT_UNIVERSE_FOR = api_defaults

#: Enough to be fast, few enough not to get throttled. See the module note.
#: Eight against the full S&P 500 drew rate limiting on about one name in
#: seven, so the default is lower and `--fill` exists to mop up the rest.
DEFAULT_WORKERS = 4

#: Workers for a fill pass. Lower still: these are the names that were already
#: refused once, and hammering them again is how a fill pass becomes a second
#: round of rate limiting.
FILL_WORKERS = 2


#: Names to probe before committing to a long run. Liquid, always-present, and
#: cheap — the point is to find out whether the provider is answering at all.
PREFLIGHT_TICKERS = ("AAPL", "MSFT", "JNJ")


def preflight(screen: str) -> str:
    """Can the provider answer at all, before we spend twenty minutes finding out?

    This exists because of a real run: 68 of 503 names came back rate-limited
    partway through, and the screen was written anyway — a complete-looking
    result with an eighth of it missing. The failure was environmental and
    detectable in three seconds, but nothing asked.

    Returns one of:
      ok        the provider answered; start the run
      degraded  it answered, but not for everything — run, and expect gaps
      offline   it answered for nothing; there is nothing to debug in the
                screen, so do not start and do not write a cache

    The three-way split is the point. Collapsing `offline` into a failure
    produces alarms nobody reads, and collapsing it into success produces a
    cache full of companies that look like they have no financials.
    """
    runner = RUNNERS[screen]
    good = 0
    for t in PREFLIGHT_TICKERS:
        try:
            row = runner(t)
        except Exception as exc:  # noqa: BLE001
            log.warning("  preflight %s raised: %s", t, str(exc)[:90])
            continue
        if not row.get("error"):
            good += 1
        else:
            log.warning("  preflight %s: %s", t, str(row.get("error"))[:90])
    if good == 0:
        return "offline"
    return "ok" if good == len(PREFLIGHT_TICKERS) else "degraded"


def run_screen(screen: str, tickers: list[str], workers: int) -> list[dict]:
    runner = RUNNERS[screen]
    started = time.time()
    out: list[dict] = []
    done = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(runner, t): t for t in tickers}
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                out.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                # Recorded, not dropped. A name that could not be checked is
                # not a name that failed the screen.
                log.warning("  %s raised: %s", ticker, exc)
                out.append({"ticker": ticker, "error": str(exc)})
            done += 1
            if done % 25 == 0 or done == len(tickers):
                rate = done / max(time.time() - started, 0.001)
                left = (len(tickers) - done) / max(rate, 0.001)
                log.info(
                    "  %s: %d/%d (%.1f/s, ~%.0fs left)",
                    screen,
                    done,
                    len(tickers),
                    rate,
                    left,
                )
    return out


def fill_errors(screen: str, universe: str, workers: int) -> int:
    """Re-run only the names the last pass could not fetch, and merge them in.

    Rate limiting is the normal failure here, and it is transient — the name is
    fine, the request was refused. Re-running the whole universe to recover one
    name in seven wastes an hour and invites the same refusal; re-running only
    the gaps, slowly, fills them.
    """
    got = cache.read(screen, universe)
    if got is None:
        log.error("no %s cache for %s to fill", screen, universe)
        return 2

    by_ticker = {r.get("ticker"): r for r in got.results if r.get("ticker")}
    failed = sorted(t for t, r in by_ticker.items() if r.get("error"))
    if not failed:
        log.info("%s/%s: nothing to fill", screen, universe)
        return 0

    log.info("%s/%s: refilling %d failed names at %d workers", screen, universe, len(failed), workers)
    started = time.time()
    refreshed = run_screen(screen, failed, workers)

    recovered = 0
    for r in refreshed:
        t = r.get("ticker")
        if not t:
            continue
        # Only replace a failure with a success. A second failure leaves the
        # first one in place, so repeated fills cannot lose a good row.
        if not r.get("error"):
            recovered += 1
        if not r.get("error") or t not in by_ticker:
            by_ticker[t] = r

    cache.write(
        screen,
        universe,
        list(by_ticker.values()),
        requested=got.requested,
        duration_s=got.duration_s + (time.time() - started),
    )
    log.info("  recovered %d of %d", recovered, len(failed))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--universe",
        default=None,
        help="universe id: sp500, sp400, sp600. Default: each screen's own.",
    )
    ap.add_argument(
        "--screen",
        action="append",
        choices=sorted(RUNNERS),
        help="screen to refresh; repeatable. Default: all.",
    )
    ap.add_argument("--max", type=int, default=0, help="cap the universe (0 = no cap)")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument(
        "--fill",
        action="store_true",
        help="only re-run names the last pass failed on, and merge them in",
    )
    ap.add_argument(
        "--no-preflight",
        action="store_true",
        help="skip the provider probe and start immediately (not recommended)",
    )
    args = ap.parse_args()

    screens = args.screen or sorted(RUNNERS)

    if args.fill:
        rc = 0
        for screen in screens:
            rc |= fill_errors(
                screen,
                args.universe or DEFAULT_UNIVERSE_FOR.get(screen, "sp500"),
                min(args.workers, FILL_WORKERS),
            )
        return rc

    rc = 0
    for screen in screens:
        # Per screen, because an explicit --universe applies to all of them but
        # the default must not: the multi-bagger screen's market-cap ceiling
        # means an S&P 500 run produces a complete, correct, entirely empty
        # result — the worst kind, since it looks like a market with nothing in
        # it rather than a screen pointed at the wrong shelf.
        universe = args.universe or DEFAULT_UNIVERSE_FOR.get(screen, "sp500")
        try:
            tickers = load_universe(universe)
        except Exception as exc:  # noqa: BLE001
            log.error("could not load universe %r: %s", universe, exc)
            rc = 2
            continue

        if args.max:
            tickers = tickers[: args.max]
        log.info(
            "%s on %s: %d tickers, %d workers",
            screen,
            universe,
            len(tickers),
            args.workers,
        )

        if not args.no_preflight:
            state = preflight(screen)
            if state == "offline":
                # Exit 0, not a failure: the environment is down, not the
                # screen. A non-zero exit here trains you to ignore the alarm.
                log.error(
                    "  preflight: offline — the data provider answered for none of %s. "
                    "Not starting, and not overwriting the existing cache.",
                    ", ".join(PREFLIGHT_TICKERS),
                )
                rc = max(rc, 0)
                continue
            if state == "degraded":
                log.warning(
                    "  preflight: degraded — expect gaps. Re-run with --fill afterwards."
                )
            else:
                log.info("  preflight: ok")

        started = time.time()
        results = run_screen(screen, tickers, args.workers)
        # Written only after the whole universe is in. A partial screen looks
        # identical to a complete one that found fewer passes.
        path = cache.write(
            screen,
            universe,
            results,
            requested=len(tickers),
            duration_s=time.time() - started,
        )
        log.info("  -> %s", path)

    return rc


if __name__ == "__main__":
    sys.exit(main())
