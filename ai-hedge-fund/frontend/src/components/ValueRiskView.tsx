import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type Intrinsic } from "@/lib/api";
import { AppNav } from "./AppNav";
import { ChatInput } from "./ChatInput";
import { ErrorBoundary } from "./ErrorBoundary";
import { DriverInput } from "./DriverInput";
import { DriverHelp } from "./DriverHelp";
import { InfoTip } from "./InfoTip";
import { ValueDistribution } from "./ValueDistribution";
import { useTicker } from "@/lib/ticker-context";
import type { GlossaryKey } from "@/lib/glossary";

/**
 * Stage 05 — what it is worth, and how sure anyone can be.
 *
 * Four numbers decide a valuation: how fast revenue grows, what margin it ends
 * up at, how much capital that growth eats, and what the money costs. This
 * screen shows those four as things you set, everything downstream as things
 * that follow, and keeps the two visually separate — that separation is the
 * point, and it was the missing piece. A page where the assumptions and the
 * results look alike invites reading a guess as a finding.
 *
 * So it is four sections, in the order the argument runs:
 *
 *   1. The verdict     what the drivers imply, against today's price
 *   2. The drivers      the four you control, plus the chance it fails
 *   3. Cost of capital  built up from the risk-free rate, not asserted
 *   4. The range        ten thousand draws, with the price marked
 *
 * A single fair value would be easier to print and worse to use. The spread is
 * the honest output: a company whose plausible values run from 90 to 160 is a
 * different proposition from one that lands on 124 every time, even when both
 * medians match.
 */

/** Percentage-shaped drivers are typed as percentages, not as 0.06. */
const pctToApi = (s: string): number | undefined => {
  const n = Number(s);
  return s.trim() === "" || !Number.isFinite(n) ? undefined : n / 100;
};
const plainToApi = (s: string): number | undefined => {
  const n = Number(s);
  return s.trim() === "" || !Number.isFinite(n) ? undefined : n;
};
const pct = (v: number | null | undefined, dp = 1) =>
  typeof v === "number" ? `${(v * 100).toFixed(dp)}%` : "—";
/** Driver keys arrive from the API in snake_case; nobody reads that. */
const humanise = (k: string) => k.replace(/_/g, " ");

const money = (v: number | null | undefined) =>
  typeof v === "number"
    ? `$${v >= 1000 ? Math.round(v).toLocaleString() : v.toFixed(2)}`
    : "—";

function Section({
  num,
  title,
  blurb,
  info,
  children,
}: {
  num: string;
  title: string;
  blurb: string;
  info?: GlossaryKey;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-sm">
      <div>
        <h2 className="flex items-baseline gap-sm font-display text-label uppercase tracking-label text-on-ink-faint">
          <span className="tabular text-cadmium">{num}</span>
          {title}
          {info && <InfoTip term={info} />}
        </h2>
        <p className="mt-2xs max-w-[72ch] text-body-sm text-on-ink-soft">
          {blurb}
        </p>
      </div>
      {children}
    </section>
  );
}

/** A figure the model produced. Deliberately plain — no box, so it cannot be
 * mistaken for something you type into. */
function Readout({
  label,
  value,
  tone,
  note,
}: {
  label: string;
  value: string;
  tone?: string;
  note?: string;
}) {
  return (
    <div className="flex flex-col gap-2xs border-l-2 border-ink-line pl-sm">
      <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
        {label}
      </span>
      <span
        className={`font-display text-display-sm tabular ${tone ?? "text-bone"}`}
      >
        {value}
      </span>
      {note && (
        <span className="max-w-[34ch] text-body-xs text-on-ink-faint">
          {note}
        </span>
      )}
    </div>
  );
}

export function ValueRiskView() {
  const { ticker: paramTicker } = useParams();
  const { goTo, recents } = useTicker();
  const ticker = paramTicker?.toUpperCase() ?? "";

  // Empty means "use whatever the endpoint derives", which is why these are
  // strings rather than numbers with defaults — a 0 would be an assertion.
  const [growth, setGrowth] = useState("");
  const [margin, setMargin] = useState("");
  const [salesToCapital, setSalesToCapital] = useState("");
  const [terminal, setTerminal] = useState("");
  const [failure, setFailure] = useState("");
  const [applied, setApplied] = useState(0);

  const params = useMemo(
    () => ({
      revenue_growth: pctToApi(growth),
      target_operating_margin: pctToApi(margin),
      sales_to_capital: plainToApi(salesToCapital),
      terminal_growth: pctToApi(terminal),
      failure_probability: pctToApi(failure),
    }),
    // Recomputed only when Revalue is pressed, so typing does not fire a
    // ten-thousand-draw simulation on every keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [applied],
  );

  // Separate from the valuation: guidance depends only on the ticker, so it is
  // not refetched every time a driver is changed and revalued.
  const guide = useQuery({
    queryKey: ["driver-guidance", ticker],
    queryFn: () => api.getDriverGuidance(ticker),
    enabled: Boolean(ticker),
    retry: false,
    staleTime: 10 * 60_000,
  });

  const q = useQuery({
    queryKey: ["intrinsic", ticker, applied],
    queryFn: () => api.getIntrinsic(ticker, params),
    enabled: Boolean(ticker),
    retry: false,
  });

  if (!ticker) {
    return (
      <div className="min-h-screen bg-ink">
        <AppNav active="research" />
        <main className="mx-auto max-w-3xl px-6 py-2xl">
          <h1 className="font-display text-display-sm tracking-tight text-bone">
            Value &amp; risk
          </h1>
          <p className="mt-sm max-w-[60ch] text-body-sm text-on-ink-soft">
            Four drivers, a cost of capital built up from the risk-free rate,
            and ten thousand draws — so the answer arrives as a range with
            today&rsquo;s price marked on it.
          </p>
          <div className="mt-lg">
            <ChatInput
              onSubmit={goTo}
              placeholder="Which company? (e.g. AAPL)"
            />
          </div>
          {recents.length > 0 && (
            <div className="mt-md flex flex-wrap items-center gap-xs">
              <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
                Recent
              </span>
              {recents.slice(0, 6).map((r: string) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => goTo(r)}
                  className="font-display text-label text-on-ink-soft transition-colors hover:text-cadmium"
                >
                  {r}
                </button>
              ))}
            </div>
          )}
        </main>
      </div>
    );
  }

  const d: Intrinsic | undefined = q.data;
  const coc = d?.cost_of_capital;
  const derived = d && !d.available ? (d.drivers ?? {}) : undefined;
  const inputs = d?.available ? d.base_case.inputs : undefined;

  // Which driver the endpoint could not work out at all. Everything else has a
  // defensible starting point; this one has none, and the valuation waits.
  const mustSupply = new Set(d && !d.available ? d.missing : []);

  const helpFor = (key: string) => {
    const entry = guide.data?.guidance.find((g) => g.key === key);
    return entry ? <DriverHelp entry={entry} /> : null;
  };

  const revalue = () => setApplied((n) => n + 1);

  return (
    <div className="min-h-screen bg-ink">
      <AppNav active="research" />

      <main className="mx-auto flex max-w-6xl flex-col gap-2xl px-6 py-lg">
        <header>
          <h1 className="font-display text-display-sm tracking-tight text-bone">
            {ticker}
            {d?.available && d.name ? (
              <span className="ml-sm font-sans text-body-sm text-on-ink-soft">
                {d.name}
              </span>
            ) : null}
          </h1>
          <p className="mt-2xs max-w-[72ch] text-body-sm text-on-ink-soft">
            Everything below follows from the four drivers in section 02. Change
            one and press revalue; nothing here is fetched from a vendor&rsquo;s
            price target.
          </p>
        </header>

        {q.isLoading && (
          <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
            Running the draws…
          </p>
        )}

        {q.error && (
          <div className="border border-oxide bg-ink-raised p-md shadow-elev-1">
            <p className="font-display text-label uppercase tracking-label text-cadmium">
              Could not value {ticker}
            </p>
            <p className="mt-xs max-w-[72ch] text-body-sm text-on-ink-soft">
              {q.error instanceof Error ? q.error.message : "unknown error"}
            </p>
          </div>
        )}

        {/* ── 01 The verdict ─────────────────────────────────────────────── */}
        {d?.available && (
          <Section
            num="01"
            title="What the drivers imply"
            info="value-per-share"
            blurb="The base case from the numbers in section 02, against what the market is asking today."
          >
            <div className="grid gap-lg border border-ink-line bg-ink-raised p-md shadow-elev-1 sm:grid-cols-2 lg:grid-cols-4">
              <Readout
                label="Value per share"
                value={money(d.base_case.value_per_share)}
                tone="text-cadmium"
              />
              <Readout label="Today's price" value={money(d.price)} />
              <Readout
                label="Median upside"
                value={
                  typeof d.distribution.median_upside_pct === "number"
                    ? `${d.distribution.median_upside_pct > 0 ? "+" : ""}${d.distribution.median_upside_pct.toFixed(1)}%`
                    : "—"
                }
                tone={
                  (d.distribution.median_upside_pct ?? 0) >= 0
                    ? "text-verdigris"
                    : "text-oxide"
                }
              />
              <Readout
                label="Draws above price"
                value={
                  typeof d.distribution.probability_value_above_price ===
                  "number"
                    ? pct(d.distribution.probability_value_above_price, 0)
                    : "—"
                }
                note={`out of ${d.distribution.runs.toLocaleString()} runs`}
              />
            </div>
            <p className="max-w-[72ch] text-body-xs text-on-ink-faint">
              {pct(d.base_case.terminal_share_of_value, 0)} of the value sits in
              the terminal year. A high share there is not an error, but it does
              mean the answer is mostly a claim about the far future.
            </p>
          </Section>
        )}

        {/* ── 02 The drivers ─────────────────────────────────────────────── */}
        <Section
          num="02"
          title="The four you control"
          blurb="Boxed fields are yours to set. Everything else on this page is worked out from them. Leave one blank to use the figure derived from the filings."
        >
          <div className="grid gap-lg border border-ink-line bg-ink-raised p-md shadow-elev-1 md:grid-cols-2 xl:grid-cols-3">
            <DriverInput
              label="Revenue growth"
              help={helpFor("revenue_growth")}
              unit="%"
              value={growth}
              onChange={setGrowth}
              required={mustSupply.has("revenue_growth")}
              derived={
                inputs?.revenue_growth != null
                  ? Number((inputs.revenue_growth * 100).toFixed(2))
                  : null
              }
              onReset={() => setGrowth("")}
              because={
                mustSupply.has("revenue_growth")
                  ? undefined
                  : "Per year, for the forecast window."
              }
              hint="No history here supports a growth rate, so this one has to be a judgment."
            />
            <DriverInput
              label="Target operating margin"
              help={helpFor("target_operating_margin")}
              unit="%"
              value={margin}
              onChange={setMargin}
              derived={
                inputs?.target_operating_margin != null
                  ? Number((inputs.target_operating_margin * 100).toFixed(2))
                  : derived?.target_operating_margin != null
                    ? Number((derived.target_operating_margin * 100).toFixed(2))
                    : null
              }
              onReset={() => setMargin("")}
              because="Where the margin settles by the end, not where it is now."
            />
            <DriverInput
              label="Sales to capital"
              help={helpFor("sales_to_capital")}
              unit="x"
              value={salesToCapital}
              onChange={setSalesToCapital}
              derived={
                inputs?.sales_to_capital != null
                  ? Number(inputs.sales_to_capital.toFixed(2))
                  : derived?.sales_to_capital != null
                    ? Number(derived.sales_to_capital.toFixed(2))
                    : null
              }
              onReset={() => setSalesToCapital("")}
              because="Revenue per dollar of capital — how much growth costs."
            />
            <DriverInput
              label="Terminal growth"
              help={helpFor("terminal_growth")}
              unit="%"
              value={terminal}
              onChange={setTerminal}
              derived={
                inputs?.terminal_growth != null
                  ? Number((inputs.terminal_growth * 100).toFixed(2))
                  : null
              }
              onReset={() => setTerminal("")}
              because="Capped at the risk-free rate: nothing outgrows the economy forever."
            />
            <DriverInput
              label="Chance it fails"
              help={helpFor("failure_probability")}
              unit="%"
              value={failure}
              onChange={setFailure}
              derived={0}
              onReset={() => setFailure("")}
              because="Probability the business does not make it, which pays out nothing."
            />
            <div className="flex items-end">
              <button
                type="button"
                onClick={revalue}
                disabled={q.isFetching}
                className="border border-ink-line px-md py-2 font-display text-label uppercase tracking-label text-bone transition-colors hover:border-cadmium hover:text-cadmium focus-visible:border-cadmium focus-visible:outline-none disabled:opacity-50"
              >
                {q.isFetching ? "Revaluing…" : "Revalue"}
              </button>
            </div>
          </div>

          {d && !d.available && (
            <div className="border border-dashed border-oxide bg-ink-raised p-md">
              <p className="font-display text-label uppercase tracking-label text-cadmium">
                No value yet
              </p>
              <p className="mt-xs max-w-[72ch] text-body-sm text-on-ink-soft">
                {d.reason}. Supply {d.missing.map(humanise).join(", ")} above
                and press revalue. Assuming a number here would produce a
                valuation that looks derived and is not.
              </p>
            </div>
          )}

          {d?.available && d.driver_notes.length > 0 && (
            <div>
              <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
                Where the starting numbers came from
              </p>
              <ul className="mt-xs flex flex-col gap-2xs">
                {d.driver_notes.map((n) => (
                  <li
                    key={n}
                    className="border-l-2 border-ink-line pl-sm text-body-xs text-on-ink-soft"
                  >
                    {n}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Section>

        {/* ── 03 Cost of capital ────────────────────────────────────────── */}
        {coc && (
          <Section
            num="03"
            title="What the money costs"
            info="cost-of-capital"
            blurb="Built up from the risk-free rate rather than asserted, so each step can be argued with separately."
          >
            <div className="border border-ink-line bg-ink-raised p-md shadow-elev-1">
              <div className="grid gap-lg sm:grid-cols-3">
                <Readout
                  label="Cost of equity"
                  value={
                    coc.cost_of_equity_pct != null
                      ? `${coc.cost_of_equity_pct.toFixed(2)}%`
                      : "—"
                  }
                />
                <Readout
                  label="After-tax cost of debt"
                  value={
                    coc.cost_of_debt_after_tax_pct != null
                      ? `${coc.cost_of_debt_after_tax_pct.toFixed(2)}%`
                      : "—"
                  }
                />
                <Readout
                  label="Used in the model"
                  value={
                    coc.wacc_pct != null
                      ? `${coc.wacc_pct.toFixed(2)}%`
                      : coc.cost_of_equity_pct != null
                        ? `${coc.cost_of_equity_pct.toFixed(2)}%`
                        : "—"
                  }
                  tone="text-cadmium"
                  note={d?.available ? d.cost_of_capital_note : undefined}
                />
              </div>

              {coc.steps?.length > 0 && (
                <ol className="mt-md flex flex-col gap-2xs border-t border-ink-line pt-sm">
                  {coc.steps.map((s, i) => (
                    <li key={s} className="flex items-baseline gap-sm">
                      <span className="w-5 shrink-0 font-display text-label tabular text-on-ink-faint">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span className="font-display text-label text-on-ink-soft">
                        {s}
                      </span>
                    </li>
                  ))}
                </ol>
              )}

              {coc.missing?.length > 0 && (
                <div className="mt-sm border-t border-ink-line pt-sm">
                  <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
                    Not available, and left out rather than guessed
                  </p>
                  <ul className="mt-2xs flex flex-col gap-2xs">
                    {coc.missing.map((m) => (
                      <li key={m} className="text-body-xs text-on-ink-soft">
                        {m}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </Section>
        )}

        {/* ── 04 The range ──────────────────────────────────────────────── */}
        {d?.available && (
          <Section
            num="04"
            title="The range, not the number"
            info="the-range"
            blurb="Each driver is drawn repeatedly within a spread, and the model is run again every time. The width is the answer."
          >
            <div className="border border-ink-line bg-ink-raised p-md shadow-elev-1">
              <ErrorBoundary>
                <ValueDistribution
                  histogram={d.distribution.histogram}
                  percentiles={d.distribution.percentiles}
                  price={d.price}
                  baseCase={d.base_case.value_per_share}
                />
              </ErrorBoundary>

              <dl className="mt-md grid gap-sm border-t border-ink-line pt-sm sm:grid-cols-3 lg:grid-cols-5">
                {["p5", "p25", "p50", "p75", "p95"].map((k) => (
                  <div key={k} className="flex flex-col">
                    <dt className="font-display text-label uppercase tracking-label text-on-ink-faint">
                      {k}
                    </dt>
                    <dd className="font-display text-mark tabular text-bone">
                      {money(d.distribution.percentiles[k])}
                    </dd>
                  </div>
                ))}
              </dl>

              {/* The caveat the simulation itself reports. Drawing the drivers
               * independently understates the spread, and the endpoint says
               * so — printing the percentiles without it would be quoting the
               * precise half of an imprecise answer. */}
              <p className="mt-sm max-w-[72ch] border-t border-ink-line pt-sm text-body-xs text-on-ink-faint">
                {d.distribution.independence_note}
              </p>
              {d.distribution.rejected > 0 && (
                <p className="mt-2xs max-w-[72ch] text-body-xs text-on-ink-faint">
                  {d.distribution.rejected.toLocaleString()} draws were
                  discarded as unusable rather than clamped into range.
                </p>
              )}
            </div>
          </Section>
        )}
      </main>
    </div>
  );
}
