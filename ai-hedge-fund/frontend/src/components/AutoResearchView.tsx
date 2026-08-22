import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppNav } from "@/components/AppNav";
import { api, type ExperimentRow } from "@/lib/api";

/**
 * Autoresearch.
 *
 * The screen is built around the thing that is easy to get wrong: a strategy
 * that looks excellent because it was chosen, from many, on the same history it
 * is being judged on. So in-sample and out-of-sample sit side by side, the bar
 * a result had to clear is shown next to the result, and discarded experiments
 * are listed rather than hidden. The count of what was tried is part of the
 * finding — a Sharpe of 1.4 means one thing as the first idea and another as
 * the best of two hundred.
 */

const num = (v: number | null | undefined, dp = 2) =>
  v === null || v === undefined || !Number.isFinite(v) ? "—" : v.toFixed(dp);

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className={`font-display text-[16px] tabular ${tone ?? "text-on-ink"}`}>{value}</div>
      <div className="font-display text-label uppercase tracking-[0.12em] text-on-ink-faint">
        {label}
      </div>
    </div>
  );
}

function ExperimentCard({ e }: { e: ExperimentRow }) {
  const ins = e.in_sample;
  const oos = e.out_of_sample;
  const verdictTone = e.is_baseline
    ? "bg-ink-line text-on-ink"
    : e.kept
      ? "bg-verdigris text-ink"
      : e.verdict === "error"
        ? "bg-oxide text-bone"
        : "bg-ink-line text-on-ink-faint";

  return (
    <article className="border-t border-ink-line px-lg py-md first:border-t-0">
      <div className="flex flex-wrap items-baseline gap-sm">
        <span className="font-display text-label tabular text-on-ink-faint">
          #{String(e.seq).padStart(2, "0")}
        </span>
        <span className={`px-2 py-0.5 font-display text-label uppercase tracking-[0.12em] ${verdictTone}`}>
          {e.is_baseline ? "baseline" : e.verdict}
        </span>
        <span className="font-display text-[14px] text-bone">{e.ticker}</span>
        <span className="font-display text-[12px] uppercase tracking-[0.1em] text-on-ink-faint">
          {e.strategy_id}
        </span>
        {e.params && Object.keys(e.params).length > 0 && (
          <span className="font-display text-label text-cadmium">
            {Object.entries(e.params).map(([k, v]) => `${k}=${v}`).join(" ")}
          </span>
        )}
        {e.overfit_flag && (
          <span className="bg-oxide/20 px-2 py-0.5 font-display text-label uppercase tracking-[0.12em] text-oxide">
            fitted the past
          </span>
        )}
      </div>

      {e.hypothesis && (
        <p className="mt-2xs max-w-[80ch] text-[13px] italic leading-relaxed text-on-ink-soft">
          {e.hypothesis}
        </p>
      )}

      {e.error ? (
        <p className="mt-sm text-[12px] text-oxide">{e.error}</p>
      ) : (
        <div className="mt-sm grid grid-cols-2 gap-md sm:grid-cols-5">
          <Metric label="in-sample sharpe" value={num(ins?.sharpe_ratio)} />
          <Metric
            label="out-of-sample sharpe"
            value={num(oos?.sharpe_ratio)}
            tone={e.kept ? "text-verdigris" : "text-on-ink"}
          />
          <Metric
            label="bar to clear"
            value={num(e.hurdle)}
            tone="text-cadmium"
          />
          <Metric label="oos return" value={`${num(oos?.total_return_pct, 1)}%`} />
          <Metric label="max drawdown" value={`${num(oos?.max_drawdown_pct, 1)}%`} />
        </div>
      )}

      {!!e.notes?.length && (
        <ul className="mt-sm space-y-0.5">
          {e.notes.map((n) => (
            <li key={n} className="text-[12px] text-cadmium/90">
              {n}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

export function AutoResearchView() {
  const qc = useQueryClient();
  const [runTag, setRunTag] = useState("");
  const [tickers, setTickers] = useState("");
  const [count, setCount] = useState(10);

  const status = useQuery({
    queryKey: ["loop-status"],
    queryFn: () => api.getLoopStatus(),
    refetchInterval: (q) => (q.state.data?.busy ? 4000 : 15000),
  });
  const busy = !!status.data?.busy;
  const activeTag = status.data?.running?.[0] ?? runTag;

  const experiments = useQuery({
    queryKey: ["experiments", activeTag],
    queryFn: () => api.getExperiments(activeTag || undefined, 200),
    refetchInterval: busy ? 4000 : false,
  });

  const start = useMutation({
    mutationFn: () =>
      api.startLoop({
        run_tag: runTag.trim(),
        tickers: tickers.split(/[,\s]+/).map((t) => t.trim().toUpperCase()).filter(Boolean),
        experiments: count,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["loop-status"] });
      qc.invalidateQueries({ queryKey: ["experiments"] });
    },
  });

  const rows = [...(experiments.data?.experiments ?? [])].sort((a, b) => b.seq - a.seq);
  const trials = rows.filter((r) => !r.is_baseline && r.verdict !== "error");
  const kept = trials.filter((r) => r.kept);

  return (
    <div className="min-h-screen bg-ink">
      <AppNav active="autoresearch" />

      <main className="mx-auto max-w-5xl px-lg py-xl">
        <header className="mb-lg">
          <h1 className="font-display text-display-sm tracking-tight text-bone">Autoresearch</h1>
          <p className="mt-sm max-w-[72ch] text-[15px] leading-relaxed text-on-ink-soft">
            Proposes one strategy at a time, evaluates it on rules it cannot change, and keeps
            it only if it beats the bar on data it was never fitted to. Discarded runs stay on
            the list — how many things were tried is part of what the survivor means.
          </p>
        </header>

        {/* Launcher */}
        <section className="border border-ink-line bg-ink-raised p-lg">
          <div className="grid gap-md sm:grid-cols-[160px_1fr_120px_auto] sm:items-end">
            <label className="block">
              <span className="mb-1 block font-display text-label uppercase tracking-[0.14em] text-on-ink-faint">
                Run tag
              </span>
              <input
                value={runTag}
                onChange={(e) => setRunTag(e.target.value)}
                placeholder="aug21"
                className="w-full border border-ink-line bg-ink px-3 py-2 font-display text-[12px] text-bone outline-none focus:border-cobalt"
              />
            </label>
            <label className="block">
              <span className="mb-1 block font-display text-label uppercase tracking-[0.14em] text-on-ink-faint">
                Tickers
              </span>
              <input
                value={tickers}
                onChange={(e) => setTickers(e.target.value)}
                placeholder="AAPL MSFT NVDA"
                className="w-full border border-ink-line bg-ink px-3 py-2 font-display text-[12px] uppercase text-bone outline-none focus:border-cobalt"
              />
            </label>
            <label className="block">
              <span className="mb-1 block font-display text-label uppercase tracking-[0.14em] text-on-ink-faint">
                Experiments
              </span>
              <input
                type="number"
                min={1}
                max={200}
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
                className="w-full border border-ink-line bg-ink px-3 py-2 font-display text-[12px] tabular text-bone outline-none focus:border-cobalt"
              />
            </label>
            <button
              type="button"
              onClick={() => start.mutate()}
              disabled={busy || !runTag.trim() || !tickers.trim() || start.isPending}
              className="bg-cobalt px-5 py-2.5 font-display text-label uppercase tracking-[0.14em] text-bone transition-colors hover:bg-cadmium hover:text-ink disabled:bg-ink-line disabled:text-on-ink-faint"
            >
              {busy ? "Running…" : "Start"}
            </button>
          </div>
          {start.isError && (
            <p className="mt-sm text-[12px] text-oxide">{(start.error as Error).message}</p>
          )}
          {busy && (
            <p className="mt-sm font-display text-label uppercase tracking-[0.12em] text-cadmium">
              Loop running — results appear below as each finishes
            </p>
          )}
        </section>

        {/* Tally */}
        {rows.length > 0 && (
          <div className="mt-lg grid gap-px bg-ink-line sm:grid-cols-4">
            {[
              { n: String(trials.length), l: "hypotheses tried", tone: "text-on-ink" },
              { n: String(kept.length), l: "survived", tone: "text-verdigris" },
              { n: String(trials.length - kept.length), l: "discarded", tone: "text-on-ink-faint" },
              {
                n: num(kept[0]?.out_of_sample?.sharpe_ratio ?? null),
                l: "best out-of-sample sharpe",
                tone: "text-cadmium",
              },
            ].map((s) => (
              <div key={s.l} className="bg-ink-raised px-lg py-md">
                <div className={`font-display text-[24px] tabular ${s.tone}`}>{s.n}</div>
                <div className="mt-2xs font-display text-label uppercase tracking-[0.14em] text-on-ink-faint">
                  {s.l}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Log */}
        <section className="mt-lg border border-ink-line bg-ink-raised">
          <div className="flex items-baseline justify-between border-b border-ink-line px-lg py-sm">
            <h2 className="font-display text-label uppercase tracking-[0.18em] text-on-ink-faint">
              Experiment log
            </h2>
            {activeTag && (
              <span className="font-display text-label text-on-ink-faint">run {activeTag}</span>
            )}
          </div>
          {rows.length === 0 ? (
            <p className="px-lg py-xl text-[13px] leading-relaxed text-on-ink-faint">
              No experiments yet. Give the run a tag, list a few tickers, and start — the
              baseline for each name is measured first, and every hypothesis after it is
              judged against that.
            </p>
          ) : (
            rows.map((e) => <ExperimentCard key={e.id} e={e} />)
          )}
        </section>
      </main>
    </div>
  );
}
