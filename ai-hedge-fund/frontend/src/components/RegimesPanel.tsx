import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import {
  num,
  pct,
  regimeColour,
  separationWord,
  shortDate,
  signed,
  spanWords,
  type RegimeAnalysis,
} from "@/lib/regimes";
import {
  EpisodeStrip,
  RegimePath,
  RegimeScatter,
  RegimeShapes,
  SeparationBars,
} from "./RegimeCharts";
import { InfoTip } from "./InfoTip";

/**
 * Analysis → Regimes. Which market the company has been in, and whether the
 * division into regimes survives being checked.
 *
 * Computed end to end: no model is called, so this answers in well under a
 * second and the same input always gives the same answer.
 *
 * The method is Horvath, Issa and Muguruza (SSRN 3947905) — cluster the *whole
 * return distribution* of each window rather than a summary of it, in
 * Wasserstein distance. The app previously labelled regimes by cutting a
 * volatility ratio at 1.25, which is one moment and a threshold nobody
 * derived.
 *
 * WHY THE VERDICT SITS AT THE TOP AND NOT IN A FOOTNOTE
 *
 * Any clustering returns clusters. Ask k-means for two groups and it produces
 * two groups whether or not two groups exist, and the resulting chart looks
 * equally convincing either way — shaded stretches, dated episodes, a
 * confident label. So the first thing on this tab is the separation ratio,
 * and it is shown next to the same score for the rule this replaces, computed
 * on identical windows with an identical kernel. When the old rule wins, it
 * says the old rule won.
 */

const WINDOWS = [
  { days: 1260, label: "5 years" },
  { days: 2520, label: "10 years" },
  { days: 5040, label: "20 years" },
] as const;

export function RegimesPanel({ ticker }: { ticker: string }) {
  const [days, setDays] = useState<number>(2520);
  const [k, setK] = useState<number>(2);

  const q = useQuery({
    queryKey: ["regimes", ticker, days, k],
    queryFn: () => api.getRegimes(ticker, { days, k }),
    staleTime: 10 * 60_000,
    retry: false,
  });

  if (q.isPending) {
    return <Notice>Clustering {ticker}&rsquo;s return distributions…</Notice>;
  }
  if (q.isError || !q.data) {
    return (
      <Notice>
        {String((q.error as Error)?.message ?? "").includes("422")
          ? `There is not enough price history for ${ticker} to fill the windows this needs. Try a shorter period.`
          : `No regime clustering for ${ticker} — the price history could not be fetched.`}
      </Notice>
    );
  }

  const d = q.data;

  return (
    <div className="flex flex-col gap-lg">
      <Controls days={days} k={k} onDays={setDays} onK={setK} data={d} />
      <Verdict data={d} />
      <WhereItHasBeen data={d} />
      <HowTheyDiffer data={d} />
      <Episodes data={d} />
      <Method data={d} />
    </div>
  );
}

// ── controls ──────────────────────────────────────────────────────────────

function Controls({
  days,
  k,
  onDays,
  onK,
  data,
}: {
  days: number;
  k: number;
  onDays: (v: number) => void;
  onK: (v: number) => void;
  data: RegimeAnalysis;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-sm">
      <p className="tabular max-w-measure text-body-xs text-on-ink-faint">
        {data.coverage.windows} overlapping {data.params.window_days}-day windows over{" "}
        {shortDate(data.coverage.first_date)} – {shortDate(data.coverage.last_date)}, fitted{" "}
        {data.fit.converged ? `to convergence in ${data.fit.iterations} passes` : "to the iteration cap"}.
      </p>
      <div className="flex flex-wrap items-center gap-md">
        <Choice legend="Period" value={days} onChange={onDays} options={WINDOWS.map((w) => ({ value: w.days, label: w.label }))} />
        <Choice
          legend="Regimes"
          value={k}
          onChange={onK}
          options={[2, 3].map((n) => ({ value: n, label: String(n) }))}
        />
      </div>
    </div>
  );
}

function Choice({
  legend,
  value,
  onChange,
  options,
}: {
  legend: string;
  value: number;
  onChange: (v: number) => void;
  options: { value: number; label: string }[];
}) {
  return (
    <fieldset className="flex items-center gap-xs border-0 p-0">
      <legend className="float-left mr-xs font-display text-label uppercase tracking-label text-on-ink-faint">
        {legend}
      </legend>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className={`rounded border px-xs py-2xs font-display text-label uppercase tracking-label transition-colors ${
            o.value === value
              ? "border-cadmium text-cadmium"
              : "border-ink-line text-on-ink-soft hover:text-bone"
          }`}
        >
          {o.label}
        </button>
      ))}
    </fieldset>
  );
}

// ── the verdict, first ────────────────────────────────────────────────────

function Verdict({ data }: { data: RegimeAnalysis }) {
  const mine = data.validation.wasserstein;
  const theirs = data.validation.volatility_ratio;
  const hmm = data.validation.hmm ?? null;
  const v = separationWord(mine.ratio);

  /* Compared against the *strongest* alternative on the page, not against the
   * weakest. Picking the volatility rule because it is the one being replaced
   * would let a hidden Markov fit outscore this method in plain sight while
   * the sentence underneath claimed a win. */
  const rivals = [
    { name: "the volatility threshold", ratio: theirs.ratio },
    ...(hmm ? [{ name: "the hidden Markov model", ratio: hmm.ratio }] : []),
  ].filter((r) => r.ratio != null && Number.isFinite(r.ratio));
  const best = rivals.sort((a, b) => (b.ratio ?? 0) - (a.ratio ?? 0))[0];
  const beat =
    best && mine.ratio != null && Number.isFinite(mine.ratio)
      ? { name: best.name, diff: mine.ratio - best.ratio! }
      : null;

  const tone =
    v.tone === "good"
      ? "text-verdigris"
      : v.tone === "weak"
        ? "text-cadmium"
        : v.tone === "unknown"
          ? "text-on-ink-faint" // missing evidence, not a failed test
          : "text-oxide";

  return (
    <section className="rounded-xl border border-ink-line bg-ink-raised p-md shadow-elev-1">
      <div className="flex flex-wrap items-baseline justify-between gap-sm">
        <h2 className="font-display text-label uppercase tracking-label text-on-ink-faint">
          Does the split hold up{" "}
          <InfoTip term="regime-separation" />
        </h2>
        <p className={`font-display text-display-sm ${tone}`}>
          {v.word}
        </p>
      </div>

      <p className="mt-xs max-w-measure text-body-sm text-on-ink-soft">
        {v.tone === "unknown" ? (
          <>
            The separation could not be measured on this history — usually one regime holds too
            few windows to compare. The regimes below are still drawn, but nothing here says
            whether they are real, so treat them as a description and no more.
          </>
        ) : v.tone === "bad" ? (
          <>
            Windows resemble the other group as much as their own. Read the regimes below as a
            description of volatility, not as evidence that {data.ticker} has two distinct
            markets — on this history it does not.
          </>
        ) : (
          <>
            Windows inside a regime look{" "}
            <span className="tabular text-bone">{num(mine.ratio)}×</span> more like each other than
            like the other regime&rsquo;s. Above 1 is the bar; this clears it
            {v.tone === "weak" ? ", but not by much" : ""}.
          </>
        )}
      </p>

      <div className="mt-md">
        <SeparationBars
          rows={[
            {
              name: "Wasserstein",
              ratio: mine.ratio,
              note: `this method · ${mine.cluster_sizes.join(" / ")} windows`,
            },
            {
              name: "Volatility ratio",
              ratio: theirs.ratio,
              note: `the rule it replaces · ${theirs.cluster_sizes.join(" / ") || "one group"}`,
            },
            // Present only when a hidden Markov model was fitted. It is scored
            // on the same windows with the same kernel, so it belongs on the
            // same axis rather than in a separate box with its own scale.
            ...(hmm
              ? [
                  {
                    name: "Hidden Markov",
                    ratio: hmm.ratio,
                    note: `the classical alternative · ${hmm.cluster_sizes.join(" / ") || "one group"}`,
                  },
                ]
              : []),
          ]}
        />
      </div>

      <p className="mt-xs max-w-measure text-body-xs text-on-ink-faint">
        {beat == null
          ? "The labellings could not all be scored on this history."
          : beat.diff > 0.15
            ? `Clustering distributions separates this name better than ${beat.name} does, by ${num(beat.diff)}.`
            : beat.diff < -0.15
              ? `On this name ${beat.name} separates better, by ${num(-beat.diff)}. That is reported rather than hidden — a score that only appeared when it flattered the method would not be worth having.`
              : `This method and ${beat.name} are within noise of each other on this name.`}{" "}
        All scored on the same {data.coverage.windows} windows, same kernel width{" "}
        <span className="tabular">{num(mine.sigma, 4)}</span>, same {mine.draws} draws.
      </p>
    </section>
  );
}

// ── where it has been ─────────────────────────────────────────────────────

function WhereItHasBeen({ data }: { data: RegimeAnalysis }) {
  const k = data.params.k;
  return (
    <section className="flex flex-col gap-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-sm">
        <h2 className="font-display text-title-xs text-bone">Where it has been</h2>
        <p className="text-body-xs text-on-ink-soft">
          Now in{" "}
          <span style={{ color: regimeColour(data.current.label, k) }} className="font-semibold">
            {data.current.name}
          </span>{" "}
          for {spanWords(data.current.run_days)}
        </p>
      </div>

      <RegimePath data={data} />

      <div className="flex flex-wrap gap-md">
        {data.centroids.map((c) => (
          <span key={c.label} className="flex items-center gap-2xs text-body-xs text-on-ink-soft">
            <span
              aria-hidden="true"
              className="inline-block h-2 w-4 rounded-sm"
              style={{ background: regimeColour(c.label, k) }}
            />
            {c.name} · {pct(c.share_pct, 0)} of the period
          </span>
        ))}
      </div>
    </section>
  );
}

// ── how the regimes differ ────────────────────────────────────────────────

function HowTheyDiffer({ data }: { data: RegimeAnalysis }) {
  const k = data.params.k;
  return (
    <section className="flex flex-col gap-sm">
      <h2 className="font-display text-title-xs text-bone">
        What tells them apart{" "}
        <InfoTip term="regime-barycentre" />
      </h2>

      <div className="grid gap-lg lg:grid-cols-2">
        <figure className="m-0">
          <figcaption className="mb-2xs text-body-xs text-on-ink-soft">
            Each regime&rsquo;s typical day, worst to best. The left end is the one a
            volatility threshold cannot see.
          </figcaption>
          <RegimeShapes centroids={data.centroids} k={k} />
        </figure>
        <figure className="m-0">
          <figcaption className="mb-2xs text-body-xs text-on-ink-soft">
            Every window by volatility and return. Crosses are the regime centres.
          </figcaption>
          <RegimeScatter data={data} />
        </figure>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[600px] border-collapse text-body-xs">
          <caption className="sr-only">Each regime summarised</caption>
          <thead>
            <tr className="border-b border-ink-line text-left font-display uppercase tracking-label text-on-ink-faint">
              <th scope="col" className="py-xs pr-md font-normal">Regime</th>
              <th scope="col" className="py-xs pr-md text-right font-normal">Windows</th>
              <th scope="col" className="py-xs pr-md text-right font-normal">Volatility</th>
              <th scope="col" className="py-xs pr-md text-right font-normal">Return a year</th>
              <th scope="col" className="py-xs pr-md text-right font-normal">Worst day</th>
              <th scope="col" className="py-xs text-right font-normal">Fat tails</th>
            </tr>
          </thead>
          <tbody>
            {data.centroids.map((c) => (
              <tr key={c.label} className="border-b border-ink-line/60">
                <th scope="row" className="py-xs pr-md text-left font-normal text-bone">
                  <span
                    aria-hidden="true"
                    className="mr-xs inline-block h-2 w-2 rounded-full align-middle"
                    style={{ background: regimeColour(c.label, k) }}
                  />
                  {c.name}
                </th>
                <td className="tabular py-xs pr-md text-right text-on-ink">
                  {c.windows} <span className="text-on-ink-faint">({pct(c.share_pct, 0)})</span>
                </td>
                <td className="tabular py-xs pr-md text-right text-on-ink">{pct(c.vol_pct)}</td>
                <td className="tabular py-xs pr-md text-right text-on-ink">{signed(c.mean_pct)}</td>
                <td className="tabular py-xs pr-md text-right text-on-ink">{pct(c.worst_day_pct, 2)}</td>
                <td className="tabular py-xs text-right text-on-ink">{num(c.kurtosis)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ── the dated stretches ───────────────────────────────────────────────────

function Episodes({ data }: { data: RegimeAnalysis }) {
  const k = data.params.k;
  const notable = [...data.episodes]
    .filter((e) => e.label > 0)
    .sort((a, b) => b.days - a.days)
    .slice(0, 6);

  return (
    <section className="flex flex-col gap-sm">
      <h2 className="font-display text-title-xs text-bone">The turbulent stretches</h2>
      <EpisodeStrip data={data} />

      {notable.length === 0 ? (
        <p className="text-body-sm text-on-ink-soft">
          No stretch of this history was labelled turbulent.
        </p>
      ) : (
        <ul className="flex flex-col gap-2xs">
          {notable.map((e, i) => (
            <li
              key={`${e.start}-${i}`}
              className="flex flex-wrap items-baseline justify-between gap-xs border-b border-ink-line/60 py-xs text-body-sm"
            >
              <span className="flex items-center gap-xs text-bone">
                <span
                  aria-hidden="true"
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ background: regimeColour(e.label, k) }}
                />
                {shortDate(e.start)} – {shortDate(e.end)}
              </span>
              <span className="tabular text-on-ink-soft">
                {e.name} · {spanWords(e.days)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ── method and limits ─────────────────────────────────────────────────────

function Method({ data }: { data: RegimeAnalysis }) {
  return (
    <section className="rounded-xl border border-ink-line p-md">
      <h2 className="font-display text-label uppercase tracking-label text-on-ink-faint">
        How this was computed, and what it will not tell you
      </h2>
      <p className="mt-xs max-w-measure text-body-sm text-on-ink-soft">
        Each {data.params.window_days}-trading-day stretch of returns is treated as a
        distribution rather than a set of summary numbers, and those distributions are
        clustered in 1-Wasserstein distance — the method of Horvath, Issa and Muguruza
        (SSRN 3947905). A regime&rsquo;s centre is the pointwise median of its members, which
        is why one crash window cannot drag it. No model is involved at any step, and the
        same inputs always give the same answer.
      </p>
      <ul className="mt-sm flex flex-col gap-xs">
        {data.caveats.map((c) => (
          <li key={c} className="flex gap-xs text-body-xs text-on-ink-faint">
            <span aria-hidden="true" className="text-oxide">
              —
            </span>
            <span className="max-w-measure">{c}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-ink-line bg-ink-raised p-md text-body-sm text-on-ink-soft shadow-elev-1">
      {children}
    </div>
  );
}
