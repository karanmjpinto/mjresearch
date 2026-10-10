import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type ScreenRow } from "@/lib/api";
import { DEFAULT_UNIVERSE_FOR } from "@/lib/universes";
import { InfoTip } from "./InfoTip";

/**
 * The names a screen found, already found.
 *
 * This page used to ask you to choose a universe and press run, then wait
 * several minutes while five hundred companies were fetched one at a time. A
 * screen is not a question you ask, it is a list you consult — and nobody
 * consults a list they have to commission first.
 *
 * So the results are computed ahead of time and this shows them on open. Which
 * makes the *date* part of the answer rather than an implementation detail:
 * these screens read quarterly fundamentals, so a run is wrong the moment a
 * company reports, and a list shown without its age invites the assumption
 * that it is current. The header carries it, and past a week it says so in
 * colour.
 *
 * Three counts, kept separate, because collapsing them is the easy lie:
 *
 *   passing   cleared the hard filters
 *   checked   returned usable data at all
 *   errored   could not be fetched — rate limiting, mostly
 *
 * A name that could not be checked has not failed the screen. Folding the
 * third number into the first would turn "we do not know" into "no".
 */

const fmt = (v: unknown, dp = 1): string => {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return v.toFixed(dp);
};

function scoreOf(row: ScreenRow, key: string): number | null {
  const v = (row as Record<string, unknown>)[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** A bar rather than a bare figure: rank is the thing being read here. */
function ScoreBar({ value, max }: { value: number | null; max: number }) {
  if (value == null) {
    return <span className="font-display text-label text-on-ink-faint">—</span>;
  }
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <span className="flex items-center gap-sm">
      <span className="h-1.5 w-16 shrink-0 bg-ink-line">
        <span className="block h-full bg-cobalt" style={{ width: `${pct}%` }} />
      </span>
      <span className="w-10 shrink-0 text-right font-display text-label tabular text-bone">
        {fmt(value, value >= 10 ? 0 : 1)}
      </span>
    </span>
  );
}

type Props = {
  screen:
    | "yartseva"
    | "acquisition-compounder"
    | "bolton-contrarian"
    | "kiyohara-handbook"
    | "ellenbogen-two-act";
  title: string;
  blurb: string;
  /** Glossary term for the heading marker. */
  info?:
    | "screen-yartseva"
    | "screen-acquisition"
    | "screen-bolton"
    | "screen-kiyohara"
    | "screen-ellenbogen";
  universe?: string;
  /** Highest possible score, for the bars. /100, except the compounder at /45. */
  scoreMax: number;
  limit?: number;
};

export function ScreenResults({
  screen,
  title,
  blurb,
  info,
  universe,
  scoreMax,
  limit = 25,
}: Props) {
  /* Per screen, not one shared default: the multi-bagger screen has a hard
   * market-cap ceiling and passes nothing at all in the S&P 500, so pointing
   * both screens at the same universe leaves one of them permanently empty. */
  const uni = universe ?? DEFAULT_UNIVERSE_FOR[screen] ?? "sp500";

  /* Needed in the failure branch, where the server's own copy of it never
   * arrived. Same shape the route returns. */
  const refreshCommand = `uv run python scripts/refresh_screens.py --universe ${uni} --screen ${screen}`;

  const q = useQuery({
    queryKey: ["screen-results", screen, uni, limit],
    queryFn: () => api.getScreenResults(screen, { universe: uni, limit }),
    retry: false,
    staleTime: 5 * 60_000,
  });

  const d = q.data;

  return (
    <section className="flex flex-col gap-sm" aria-label={title}>
      <div className="flex flex-wrap items-baseline justify-between gap-md">
        <div>
          <h2 className="flex items-center gap-xs font-display text-label uppercase tracking-label text-on-ink-faint">
            {title}
            {info && <InfoTip term={info} />}
          </h2>
          <p className="mt-2xs max-w-measure text-body-sm text-on-ink-soft">
            {blurb}
          </p>
        </div>

        {d?.available && (
          <div className="shrink-0 text-right">
            <p
              className={`font-display text-label uppercase tracking-label ${
                d.stale ? "text-cadmium" : "text-on-ink-faint"
              }`}
            >
              {d.age_days != null && d.age_days < 1
                ? "Built today"
                : `Built ${Math.round(d.age_days ?? 0)} days ago`}
              {d.stale && " · worth refreshing"}
            </p>
            {/* A second kind of stale, and the more dangerous one, because a
              * recent date actively argues against it. These rows were scored
              * by rules the screen no longer applies: when the market-cap band
              * was added, 398 of the 503 names in the cached S&P 500 run became
              * companies that would now be rejected on size, while the file
              * went on reporting them as passes dated that morning.
              *
              * Cadmium rather than a neutral tone because this one invalidates
              * the rows themselves rather than merely ageing them. */}
            {/* Two deliberate lines rather than one wrapped one. At this
              * column width a single string broke after the separator and
              * left a middot orphaned at the start of a line. The fact and
              * the instruction are different sentences anyway. */}
            {d.criteria_changed && (
              <p className="mt-2xs font-display text-label uppercase leading-tight tracking-label text-cadmium">
                <span className="block">Scored under older rules</span>
                <span className="block text-on-ink-faint">Rebuild before trusting</span>
              </p>
            )}
            <p className="mt-2xs font-display text-label tabular text-on-ink-soft">
              {d.passing} of {d.checked} passed
              {d.errored > 0 && (
                <span className="text-on-ink-faint">
                  {" "}
                  · {d.errored} unfetchable
                </span>
              )}
            </p>
          </div>
        )}
      </div>

      {q.isLoading && (
        <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
          Reading the last run…
        </p>
      )}

      {q.error && (
        /* Every other branch here hands the reader something to do — the
         * uncomputed one prints the command, the empty one explains the
         * dominant failure. This one printed a message and stopped, which is
         * the one case where the reader is actually stuck. `retry: false`
         * means nothing is happening in the background either, so the retry
         * has to be a control. */
        <div className="border border-oxide bg-ink-raised p-md">
          <p className="font-display text-label uppercase tracking-label text-oxide">
            Could not read the screen
          </p>
          <p className="mt-xs max-w-measure text-body-sm text-on-ink-soft">
            {q.error instanceof Error ? q.error.message : "The request failed."}
          </p>
          <button
            type="button"
            onClick={() => void q.refetch()}
            disabled={q.isFetching}
            className="mt-sm border border-ink-line px-sm py-2xs font-display text-label uppercase tracking-label text-bone transition-colors hover:border-cobalt hover:text-cobalt disabled:opacity-50"
          >
            {q.isFetching ? "Trying…" : "Try again"}
          </button>
          <p className="mt-sm max-w-measure text-body-xs text-on-ink-faint">
            If it keeps failing, the screen may never have been built. Compute
            it with{" "}
            <span className="font-display text-on-ink-soft">
              {refreshCommand}
            </span>
            .
          </p>
        </div>
      )}

      {d?.available === false && (
        /* Not an error state. Nothing has been computed yet, and the fix is one
         * command rather than a button — the run takes minutes, and a web
         * request that holds a connection open that long is a worse design
         * than telling someone what to type. */
        <div className="border border-dashed border-ink-line bg-ink-raised p-md">
          <p className="font-display text-label uppercase tracking-label text-cadmium">
            Nothing computed yet
          </p>
          <p className="mt-xs max-w-measure text-body-sm text-on-ink-soft">
            {d.reason}
          </p>
          <pre className="mt-sm overflow-x-auto border border-ink-line bg-ink p-sm font-display text-label text-on-ink-soft">
            {d.refresh_command}
          </pre>
        </div>
      )}

      {d?.available && d.results.length === 0 && (
        /* An empty screen has to say why. "0 of 503 passed" is a dead end;
         * the dominant failure reason usually says the screen is pointed at
         * the wrong universe, which is worth knowing. */
        <div className="border border-dashed border-ink-line bg-ink-raised p-md">
          <p className="font-display text-label uppercase tracking-label text-cadmium">
            Nothing passed, and here is why
          </p>
          <p className="mt-xs max-w-measure text-body-sm text-on-ink-soft">
            None of the {d.checked} names this screen could read cleared its
            hard filters.
          </p>
          {d.top_failures?.length > 0 && (
            <ul className="mt-sm flex flex-col gap-2xs">
              {d.top_failures.map((f) => (
                <li key={f.reason} className="flex items-baseline gap-sm">
                  <span className="w-12 shrink-0 text-right font-display text-label tabular text-oxide">
                    {f.count}
                  </span>
                  <span className="text-body-xs text-on-ink-soft">
                    {f.reason}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {d.top_failures?.[0] && d.top_failures[0].count > d.checked * 0.9 && (
            /* One reason knocking out almost everything is not a screen that
             * found nothing — it is a screen aimed at the wrong list. */
            <p className="mt-sm max-w-measure border-t border-ink-line pt-sm text-body-xs text-cadmium">
              Almost every name failed on the same rule, which means this
              universe is the wrong one for this screen rather than a market
              with nothing in it. Use the panel below to point it somewhere that
              fits.
            </p>
          )}
        </div>
      )}

      {d?.available && d.results.length > 0 && (
        <div className="overflow-x-auto border border-ink-line bg-ink-raised shadow-elev-1">
          <table className="w-full min-w-[520px] border-collapse">
            <caption className="sr-only">
              {title}: top {d.shown} of {d.passing} passing names
            </caption>
            <thead>
              <tr className="border-b border-ink-line">
                <th className="px-md py-xs text-left font-display text-label uppercase tracking-label text-on-ink-faint">
                  Ticker
                </th>
                <th className="px-md py-xs text-left font-display text-label uppercase tracking-label text-on-ink-faint">
                  Score
                </th>
                <th className="px-md py-xs text-left font-display text-label uppercase tracking-label text-on-ink-faint">
                  Why it is here
                </th>
              </tr>
            </thead>
            <tbody>
              {d.results.map((r, i) => {
                const t = String(r.ticker ?? "").toUpperCase();
                return (
                  <tr
                    key={`${t}-${i}`}
                    className="border-b border-ink-line last:border-b-0"
                  >
                    <td className="px-md py-xs">
                      {t ? (
                        <Link
                          to={`/research/${encodeURIComponent(t)}`}
                          className="font-display text-mark text-cobalt transition-colors hover:text-cadmium"
                        >
                          {t}
                        </Link>
                      ) : (
                        <span className="font-display text-mark text-on-ink-faint">
                          —
                        </span>
                      )}
                    </td>
                    <td className="px-md py-xs">
                      <ScoreBar
                        value={scoreOf(r, d.score_key)}
                        max={scoreMax}
                      />
                    </td>
                    {/* Capped narrower than the app's measure: this cell now
                     * carries a sentence's worth of evidence, and without a
                     * bound it absorbs the table's slack on a wide screen and
                     * out-runs every paragraph on the page. */}
                    <td className="px-md py-xs text-body-xs text-on-ink-soft">
                      <span className="block max-w-measure-sm">
                        {reason(r)}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {d?.available && (
        <p className="max-w-measure text-body-xs text-on-ink-faint">
          Figures come from yfinance quarterly data, so verify against the
          filings before acting on any of it. Refresh with{" "}
          <span className="font-display text-on-ink-soft">
            {d.refresh_command}
          </span>
          .
        </p>
      )}
    </section>
  );
}

/**
 * One line on why a name is in the list.
 *
 * The screens return dozens of fields each and the old panels printed most of
 * them, which is how a screen becomes unreadable: forty numbers per row is not
 * evidence, it is a spreadsheet nobody scans. This picks the two or three that
 * carry the verdict and leaves the rest to the company's own page.
 */
function reason(r: ScreenRow): string {
  const bits: string[] = [];
  const top = r as Record<string, unknown>;
  const snap = (r.snapshot ?? {}) as Record<string, unknown>;

  /** The compounder stores rates as fractions; the Yartseva screen as
   *  percentages already. Mixing the two prints a 39% ROIC as "0.4%". */
  const rate = (obj: Record<string, unknown>, key: string, label: string) => {
    const v = obj[key];
    if (typeof v === "number" && Number.isFinite(v)) {
      bits.push(`${label} ${(v * 100).toFixed(0)}%`);
    }
  };
  const pct = (
    obj: Record<string, unknown>,
    key: string,
    label: string,
    dp = 1,
  ) => {
    const v = obj[key];
    if (typeof v === "number" && Number.isFinite(v))
      bits.push(`${label} ${v.toFixed(dp)}%`);
  };
  const raw = (
    obj: Record<string, unknown>,
    key: string,
    label: string,
    dp = 2,
  ) => {
    const v = obj[key];
    if (typeof v === "number" && Number.isFinite(v))
      bits.push(`${label} ${v.toFixed(dp)}`);
  };

  // Compounder: fractions in `snapshot`.
  rate(snap, "roic", "ROIC");
  /* The reinvestment leg, next to ROIC on purpose: the pair is the point.
   * ROIC says what the capital already deployed earns; this says what the
   * business can compound at from its own cash. A high ROIC beside a 2%
   * implied rate is a good business with nowhere to put the next dollar,
   * and that is a distinction worth seeing without opening the row. */
  rate(snap, "implied_compounding", "implied compounding");
  rate(snap, "revenue_cagr_5y", "5y revenue");
  raw(snap, "net_debt_to_ebitda", "net debt/EBITDA", 1);

  // Yartseva: percentages at the top level.
  pct(top, "ebitda_growth_pct", "EBITDA growth", 0);
  pct(top, "fcf_yield_pct", "FCF yield");
  raw(top, "book_to_market", "book/market");

  // Bolton: the interesting facts are which measures are cheap and how far
  // the market has walked away, not another ratio. `cheap_on` arrives
  // pre-formatted from the screen, so it is not re-derived here.
  const cheap = top.cheap_on as unknown as string[] | undefined;
  if (Array.isArray(cheap) && cheap.length > 0) {
    // Two, then say how many more. Truncating silently reported a company
    // cheap on four measures as cheap on two, which understates the only
    // thing this column exists to show.
    const shown = cheap.slice(0, 2).join(" · ");
    const rest = cheap.length - 2;
    bits.push(rest > 0 ? `${shown} +${rest} more` : shown);
  }
  const pos = top.range_position;
  if (typeof pos === "number" && Number.isFinite(pos)) {
    bits.push(`${Math.round(pos * 100)}% up its 52w range`);
  }
  const shorted = top.short_percent_float;
  if (
    typeof shorted === "number" &&
    Number.isFinite(shorted) &&
    shorted >= 0.05
  ) {
    bits.push(`${(shorted * 100).toFixed(0)}% short`);
  }
  const insider = top.insider_net_12m;
  if (typeof insider === "number" && insider > 0) {
    bits.push(`${insider} net insider buy${insider === 1 ? "" : "s"}`);
  }

  /* Kiyohara: the multiple he actually works from, and the two balance-sheet
   * facts behind it. `tiers_cleared` is the honest half of the P/E test — the
   * screen reports which of his four ceilings a name is under because
   * choosing one would mean claiming to know the business type it says on
   * every row it has not checked. */
  const pe2 = top.pe_second_year;
  if (typeof pe2 === "number" && Number.isFinite(pe2)) {
    bits.push(`${pe2.toFixed(1)}x 2nd-yr`);
  }
  const tiers = top.tiers_cleared as unknown as string[] | undefined;
  if (Array.isArray(tiers) && tiers.length > 0) {
    /* How many of his four ceilings, not which. Naming the strictest one
     * cleared would print "under his small/mid real estate ceiling" against a
     * machinery company — a sector claim the screen has not made. The count
     * says the same thing without asserting a business type, and the
     * thresholds stay in one place, in the screen. */
    bits.push(`under ${tiers.length} of his 4 P/E ceilings`);
  }
  const equityRatio = top.equity_ratio;
  if (typeof equityRatio === "number" && Number.isFinite(equityRatio)) {
    bits.push(`${Math.round(equityRatio * 100)}% equity ratio`);
  }
  const netCash = top.net_cash_ratio;
  if (typeof netCash === "number" && Number.isFinite(netCash) && netCash > 0) {
    bits.push(`net cash ${Math.round(netCash * 100)}% of cap`);
  }
  if (top.equity_issued_recently === true) {
    bits.push("has issued equity");
  }

  /* Ellenbogen: the slope, not the level. His research found compounders got
   * better as they got bigger, so the change in return on capital is the
   * first thing worth seeing — and the row has to say when that change was
   * not measurable, because a neutral score and a measured mediocre one look
   * identical otherwise. The drawdown is here for the same reason it is
   * unscored: it marks where the failing-or-transitioning question gets
   * asked. */
  const roicChange = top.roic_change_pp;
  if (
    typeof roicChange === "number" &&
    Number.isFinite(roicChange) &&
    top.roic_slope_measured === true
  ) {
    const sign = roicChange >= 0 ? "+" : "";
    bits.push(`ROIC ${sign}${roicChange.toFixed(1)}pp as it grew`);
  } else if (typeof top.roic_slope_unmeasured_reason === "string") {
    bits.push(
      `slope not measured (${top.roic_slope_unmeasured_reason.replace(/_/g, " ")})`,
    );
  }
  /* Found on a real name: years of buybacks leave invested capital near zero
   * and the ratio prints in the hundreds of percent. Saying so beats printing
   * it. */
  if (top.roic_level_measured === false) {
    bits.push("ROIC unrankable — capital base bought back");
  }
  const gap = top.gap_to_compounder_bar_pp;
  if (typeof gap === "number" && Number.isFinite(gap)) {
    bits.push(
      gap <= 0
        ? `${(-gap).toFixed(0)}pp past his 20% bar`
        : `${gap.toFixed(0)}pp short of his 20% bar`,
    );
  }
  const dd = top.drawdown_from_5y_high;
  if (typeof dd === "number" && Number.isFinite(dd) && dd >= 0.2) {
    bits.push(`${Math.round(dd * 100)}% off its 5y high`);
  }
  if (top.transition_candidate === true) {
    bits.push("transition candidate — not a buy");
  }

  const flags = r.red_flags;
  if (Array.isArray(flags) && flags.length > 0) {
    bits.push(`${flags.length} red flag${flags.length === 1 ? "" : "s"}`);
  }

  return bits.length ? bits.join(" · ") : "Cleared the hard filters.";
}
