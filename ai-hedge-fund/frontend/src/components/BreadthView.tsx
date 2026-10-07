import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { AppNav } from "./AppNav";
import { InfoTip } from "./InfoTip";
import { BreadthChart } from "./BreadthChart";
import {
  HORIZONS,
  pct1,
  shortDate,
  signed1,
  stanceTone,
  type BreadthResponse,
} from "@/lib/breadth";

/**
 * Market breadth — the one screen here that is about the market rather than a
 * company.
 *
 * It exists because of a specific claim, which is worth stating plainly before
 * the numbers: that an index making new highs while fewer and fewer of its
 * members participate is a warning, and that this warning preceded 1929, 1962,
 * 1973 and 1987. The measurement half of that claim is arithmetic and this
 * screen does it exactly. The predictive half is an empirical question, and
 * the answer in the only history that can be built here is *no* — which is
 * why the verdict sits above the chart rather than below the episode table.
 *
 * ORDER OF THE PAGE, AND WHY
 *
 *   1  Is it diverging right now — the thing someone opened the screen for.
 *   2  The verdict on whether that has meant anything, before the chart gets
 *      a chance to be persuasive. A divergence chart is extremely convincing
 *      to look at; that is the problem with it.
 *   3  The chart.
 *   4  The thresholds, movable, because the finding depends on them and a
 *      reader who cannot move them has to take the default on trust.
 *   5  Episodes and base rates — the evidence for 2.
 *   6  What would make all of it wrong.
 *
 * No model is called anywhere in this. The same inputs give the same screen.
 */

export function BreadthView() {
  const [near, setNear] = useState(2);
  const [floor, setFloor] = useState(50);

  const q = useQuery({
    queryKey: ["breadth", near, floor],
    queryFn: () => api.getBreadth({ near, floor }),
    staleTime: 10 * 60_000,
    retry: false,
  });

  return (
    <div className="min-h-screen bg-ink">
      <AppNav active="breadth" />
      <main className="mx-auto flex max-w-5xl flex-col gap-lg px-md py-lg">
        <header className="flex flex-col gap-xs">
          <h1 className="font-display text-xl uppercase tracking-label text-bone">
            Market breadth
          </h1>
          <p className="max-w-2xl text-sm text-on-ink-soft">
            Whether the index is making highs its own members are not — and what
            that has been worth knowing.
            <InfoTip term="breadth-divergence" />
          </p>
        </header>

        {q.isPending && <Notice>Reading the breadth series…</Notice>}
        {q.isError && (
          <Notice>
            {String((q.error as Error)?.message ?? "").includes("503")
              ? "No breadth series has been built on this server yet. Build it with: uv run python scripts/refresh_breadth.py"
              : `The breadth series could not be read — ${(q.error as Error)?.message ?? "unknown error"}`}
          </Notice>
        )}

        {q.data && (
          <>
            <Reading data={q.data} />
            <Verdict data={q.data} />
            <section className="border border-ink-line p-md">
              <BreadthChart data={q.data} />
            </section>
            <Thresholds
              near={near}
              floor={floor}
              onNear={setNear}
              onFloor={setFloor}
              data={q.data}
            />
            <BaseRates data={q.data} />
            <Episodes data={q.data} />
            <Limits data={q.data} />
            <Source data={q.data} />
          </>
        )}
      </main>
    </div>
  );
}

// ── 1. where it stands today ──────────────────────────────────────────────

function Reading({ data }: { data: BreadthResponse }) {
  const r = data.reading;
  return (
    <section className="flex flex-col gap-sm border border-ink-line p-md">
      <p className="font-display text-label uppercase tracking-label text-on-ink-soft">
        {shortDate(r.date)} · {r.members} members
      </p>
      <p className="text-lg text-bone">
        {r.divergent ? (
          <>
            The index is <strong className="text-cadmium">within {Math.abs(r.index_gap_pct).toFixed(1)}%</strong>{" "}
            of its one-year high while only{" "}
            <strong className="text-oxide">{r.pct_above_200dma.toFixed(0)}%</strong>{" "}
            of its members are above their own 200-day average.
          </>
        ) : (
          <>
            No divergence by the thresholds set below: the index is{" "}
            {Math.abs(r.index_gap_pct).toFixed(1)}% off its one-year high with{" "}
            {r.pct_above_200dma.toFixed(0)}% of members above their 200-day average.
          </>
        )}
      </p>
      <dl className="grid grid-cols-2 gap-sm sm:grid-cols-4">
        <Stat label="Index vs 1-year high" value={signed1(r.index_gap_pct)} />
        <Stat label="Members above 200-day" value={pct1(r.pct_above_200dma)} />
        <Stat
          label="New highs less new lows"
          value={signed1(r.net_new_highs_pct)}
          note="share of members"
        />
        <Stat
          label="A-D line peaked"
          value={`${r.days_since_ad_peak}d ago`}
          note={shortDate(r.ad_line_peak_date)}
        />
      </dl>
    </section>
  );
}

function Stat({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="font-display text-label uppercase tracking-label text-on-ink-soft">
        {label}
      </dt>
      <dd className="text-lg text-bone tabular">{value}</dd>
      {note && <dd className="text-label text-on-ink-soft tabular">{note}</dd>}
    </div>
  );
}

// ── 2. whether it has meant anything ──────────────────────────────────────

function Verdict({ data }: { data: BreadthResponse }) {
  const v = data.verdict;
  const c = data.coverage;
  return (
    /* A full border, like every other block on the page. This was a left rule,
     * on the reasoning that the verdict is a pull quote — but in a page where
     * every other section is a bordered card, one left-ruled block reads as an
     * inconsistency rather than as emphasis. The verdict earns its place by
     * sitting second and by being the only coloured sentence, which is
     * hierarchy made of type rather than of a second border idiom. */
    <section className="flex flex-col gap-xs border border-ink-line p-md">
      <p className="font-display text-label uppercase tracking-label text-on-ink-soft">
        Has it mattered
        <InfoTip term="breadth-base-rate" />
      </p>
      <p className={`text-base ${stanceTone[v.stance]}`}>{v.line}</p>
      <p className="text-label text-on-ink-soft">
        {c.episodes} episode{c.episodes === 1 ? "" : "s"} over {c.sessions.toLocaleString()}{" "}
        sessions, {shortDate(c.first_session)} to {shortDate(c.last_session)}. The
        divergences this warning was built on — 1929, 1962, 1973, 1987 — are
        outside that window, and no free source of index membership reaches
        them. Nothing here tests the original claim.
      </p>
    </section>
  );
}

// ── 4. the knobs, visible ─────────────────────────────────────────────────

function Thresholds({
  near,
  floor,
  onNear,
  onFloor,
  data,
}: {
  near: number;
  floor: number;
  onNear: (v: number) => void;
  onFloor: (v: number) => void;
  data: BreadthResponse;
}) {
  return (
    <section className="flex flex-col gap-sm border border-ink-line p-md">
      <p className="font-display text-label uppercase tracking-label text-on-ink-soft">
        Where the line is drawn
      </p>
      <p className="max-w-2xl text-sm text-on-ink-soft">
        Neither threshold is derived from anything. They are conventions, and
        the episode count moves by an order of magnitude across the range —
        which is the most useful thing on this screen, and the reason they are
        controls rather than constants.
      </p>
      <div className="flex flex-wrap gap-lg">
        <Choice
          label="Index no more than"
          suffix="below its 1-year high"
          value={near}
          options={[1, 2, 5]}
          onChange={onNear}
          unit="%"
        />
        <Choice
          label="Members above their 200-day"
          suffix="or fewer"
          value={floor}
          options={[50, 55, 60, 65]}
          onChange={onFloor}
          unit="%"
        />
      </div>
      <p className="text-label text-on-ink-soft tabular">
        {data.coverage.signal_days} signal day
        {data.coverage.signal_days === 1 ? "" : "s"} in {data.coverage.episodes}{" "}
        episode{data.coverage.episodes === 1 ? "" : "s"}.
      </p>
    </section>
  );
}

function Choice({
  label,
  suffix,
  value,
  options,
  onChange,
  unit,
}: {
  label: string;
  suffix: string;
  value: number;
  options: number[];
  onChange: (v: number) => void;
  unit: string;
}) {
  return (
    <fieldset className="flex flex-col gap-xs">
      <legend className="font-display text-label uppercase tracking-label text-on-ink-soft">
        {label} {suffix}
      </legend>
      <div className="flex gap-xs">
        {options.map((o) => (
          <button
            key={o}
            type="button"
            onClick={() => onChange(o)}
            aria-pressed={o === value}
            className={`border px-sm py-1 font-display text-label tabular transition-colors ${
              o === value
                ? "border-cobalt text-bone"
                : "border-ink-line text-on-ink-soft hover:border-cobalt hover:text-bone"
            }`}
          >
            {o}
            {unit}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

// ── 5. the evidence ───────────────────────────────────────────────────────

function BaseRates({ data }: { data: BreadthResponse }) {
  return (
    <section className="flex flex-col gap-sm">
      <h2 className="font-display text-label uppercase tracking-label text-on-ink-soft">
        What followed, against what usually follows
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[32rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-ink-line text-left font-display text-label uppercase tracking-label text-on-ink-soft">
              <th className="py-xs pr-sm font-normal">Horizon</th>
              <th className="py-xs pr-sm font-normal">After a divergence</th>
              <th className="py-xs pr-sm font-normal">Hit rate</th>
              <th className="py-xs pr-sm font-normal">Any day</th>
              <th className="py-xs pr-sm font-normal">Hit rate</th>
              <th className="py-xs font-normal">Episodes</th>
            </tr>
          </thead>
          <tbody>
            {HORIZONS.map(({ key, label }) => {
              const row = data.base_rates[key];
              if (!row) return null;
              const a = row.after_divergence;
              const u = row.unconditional;
              return (
                <tr key={key} className="border-b border-ink-line/50 text-bone">
                  <td className="py-xs pr-sm">{label}</td>
                  <td className="py-xs pr-sm tabular">{signed1(a.median)}</td>
                  <td className="py-xs pr-sm tabular text-on-ink-soft">{pct1(a.hit_rate)}</td>
                  <td className="py-xs pr-sm tabular text-on-ink-soft">{signed1(u.median)}</td>
                  <td className="py-xs pr-sm tabular text-on-ink-soft">{pct1(u.hit_rate)}</td>
                  <td className="py-xs tabular">{a.n}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="max-w-2xl text-label text-on-ink-soft">
        Medians, not means: at these sample sizes one 2008 observation moves a
        mean further than the rest of the sample combined. The last column is
        the number of episodes with a full horizon after them — read every row
        against it, because a median over four observations is compatible with
        almost any claim.
      </p>
    </section>
  );
}

function Episodes({ data }: { data: BreadthResponse }) {
  if (!data.episodes.length) {
    return (
      <p className="text-sm text-on-ink-soft">
        No episode in this history meets both thresholds. Loosen them above.
      </p>
    );
  }
  return (
    <section className="flex flex-col gap-sm">
      <h2 className="font-display text-label uppercase tracking-label text-on-ink-soft">
        Every episode
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[34rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-ink-line text-left font-display text-label uppercase tracking-label text-on-ink-soft">
              <th className="py-xs pr-sm font-normal">Began</th>
              <th className="py-xs pr-sm font-normal">Days</th>
              <th className="py-xs pr-sm font-normal">Above 200-day</th>
              {HORIZONS.map((h) => (
                <th key={h.key} className="py-xs pr-sm font-normal">
                  {h.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.episodes.map((e) => (
              <tr key={e.start} className="border-b border-ink-line/50 text-bone">
                <td className="py-xs pr-sm tabular">{shortDate(e.start)}</td>
                <td className="py-xs pr-sm tabular text-on-ink-soft">{e.days}</td>
                <td className="py-xs pr-sm tabular text-on-ink-soft">
                  {pct1(e.pct_above_at_start)}
                </td>
                {HORIZONS.map((h) => {
                  const v = e.forward[h.key];
                  return (
                    <td
                      key={h.key}
                      className={`py-xs pr-sm tabular ${
                        v == null
                          ? "text-on-ink-soft"
                          : v < 0
                            ? "text-oxide"
                            : "text-verdigris"
                      }`}
                    >
                      {v == null ? "not yet" : signed1(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-label text-on-ink-soft">
        &ldquo;Not yet&rdquo; is an episode whose horizon has not finished — including,
        when it is live, the one happening now.
      </p>
    </section>
  );
}

// ── 6. what would make it wrong ───────────────────────────────────────────

function Limits({ data }: { data: BreadthResponse }) {
  return (
    <section className="flex flex-col gap-sm border border-ink-line p-md">
      <h2 className="font-display text-label uppercase tracking-label text-on-ink-soft">
        What would make this wrong
      </h2>
      <dl className="flex flex-col gap-sm">
        {data.limits.map((l) => (
          <div key={l.title} className="flex flex-col gap-0.5">
            <dt className="text-sm text-bone">{l.title}</dt>
            <dd className="max-w-2xl text-sm text-on-ink-soft">{l.body}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Source({ data }: { data: BreadthResponse }) {
  const s = data.source;
  return (
    <p className="font-display text-label uppercase tracking-label text-on-ink-soft">
      {s.universe} · index {s.index_symbol} · built{" "}
      {new Date(s.built_at).toLocaleString()}
      {s.stale && (
        <span className="text-oxide"> · stale, rebuild with {s.refresh}</span>
      )}
    </p>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <p className="border border-ink-line p-md text-sm text-on-ink-soft">{children}</p>
  );
}
