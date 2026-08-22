import { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { ChatInput } from "./ChatInput";
import { AppNav } from "./AppNav";
import { useTicker } from "@/lib/ticker-context";

export function Dashboard() {
  const navigate = useNavigate();
  const { recents } = useTicker();
  const [watchGroup, setWatchGroup] = useState<string>("default");

  const watchlists = useQuery({ queryKey: ["watchlists"], queryFn: api.getWatchlists });
  const portfolio = useQuery({ queryKey: ["portfolio"], queryFn: api.getPortfolio, retry: false });
  const sectors = useQuery({
    queryKey: ["sector-performance"],
    queryFn: api.getSectorPerformance,
    retry: false,
  });
  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: api.getProviderStatus,
    retry: false,
  });
  // What the dashboard is actually for: picking up work, not reading a brochure.
  const recentRuns = useQuery({
    queryKey: ["recent-runs"],
    queryFn: () => api.getRuns(undefined, 6),
    retry: false,
  });
  const recentDecisions = useQuery({
    queryKey: ["recent-decisions"],
    queryFn: () => api.getDecisions(undefined, 6),
    retry: false,
  });

  const groupKeys = useMemo(
    () => (watchlists.data ? Object.keys(watchlists.data) : []),
    [watchlists.data],
  );

  useEffect(() => {
    if (groupKeys.length && !groupKeys.includes(watchGroup)) {
      setWatchGroup(groupKeys[0]!);
    }
  }, [groupKeys, watchGroup]);

  const handleSearch = (query: string) => {
    const ticker = query.replace(/^check\s+/i, "").trim().toUpperCase();
    if (ticker) navigate(`/research/${ticker}`);
  };

  const sectorData =
    sectors.data?.realtime ??
    sectors.data?.one_day ??
    sectors.data?.five_day ??
    [];
  const sectorLabel = sectors.data?.realtime
    ? "Real-time"
    : sectors.data?.one_day
      ? "1 Day"
      : "5 Day";

  const activeProviders = providers.data?.providers.filter((p) => p.available).length ?? 0;
  const totalProviders = providers.data?.providers.length ?? 0;
  const tickers = watchlists.data?.[watchGroup] ?? [];

  return (
    <div className="flex flex-col h-dvh">
      <AppNav
        active="home"
        end={<span className="text-xs text-gray-600 font-mono">Ollama · yfinance · EDGAR · MCP</span>}
      />

      <div className="grow overflow-y-auto">
        <div className="max-w-6xl mx-auto px-6 py-8 flex flex-col gap-8">
          {/* Hero — start work, do not describe the product */}
          <section className="flex flex-col gap-sm">
            <h1 className="font-display text-display-sm tracking-tight text-bone">
              What are you looking at?
            </h1>
            <p className="max-w-2xl text-[15px] leading-relaxed text-on-ink-soft">
              Research a name, form a view over numbers the model did not produce, size it
              against the book you already hold, and record the call. Everything runs on this
              machine.
            </p>
            <div className="mt-2xs max-w-xl">
              <ChatInput onSubmit={handleSearch} placeholder="Research a ticker (e.g. AAPL, NVDA, 7203.T)" />
            </div>
            {recents.length > 0 && (
              <div className="mt-2xs flex flex-wrap items-center gap-2xs">
                <span className="font-display text-label uppercase tracking-[0.16em] text-on-ink-faint">
                  Recent
                </span>
                {recents.slice(0, 6).map((r: string) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => navigate(`/research/${r}`)}
                    className="px-2 py-1 font-display text-[12px] text-on-ink-faint transition-colors hover:text-cadmium"
                  >
                    {r}
                  </button>
                ))}
              </div>
            )}
          </section>

          {/* Snapshot strip — portfolio + providers + sector drift */}
          <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <SnapshotCard
              label="Book value"
              value={
                portfolio.data
                  ? `$${portfolio.data.total_value.toLocaleString()}`
                  : "—"
              }
              sub={portfolio.data ? "Live SQLite book" : "No positions yet"}
              href="/portfolio"
              cta="Manage portfolio →"
            />
            <SnapshotCard
              label="Data providers"
              value={`${activeProviders} / ${totalProviders}`}
              sub="Active / configured"
              href="#providers"
              cta="See stack ↓"
            />
            <SnapshotCard
              label={`Sector drift (${sectorLabel.toLowerCase()})`}
              value={
                sectors.isPending
                  ? "—"
                  : sectorData.length > 0
                    ? `${sectorData[0].sector}: ${sectorData[0].change_pct >= 0 ? "+" : ""}${sectorData[0].change_pct.toFixed(2)}%`
                    : "—"
              }
              sub={sectors.isPending ? "Loading…" : sectorData.length > 0 ? "Top mover today" : "Unavailable"}
              href="#sectors"
              cta={sectorData.length > 0 ? "All sectors ↓" : ""}
            />
          </section>

          {/* Work in progress — the two things worth resuming */}
          <section className="grid grid-cols-1 gap-lg lg:grid-cols-2">
            <div className="border border-ink-line bg-ink-raised">
              <div className="flex items-baseline justify-between border-b border-ink-line px-lg py-sm">
                <h2 className="font-display text-label uppercase tracking-[0.18em] text-on-ink-faint">
                  Recent research
                </h2>
                <span className="font-display text-label uppercase tracking-[0.14em] text-on-ink-faint">
                  {recentRuns.data?.count ?? 0} runs
                </span>
              </div>
              {(recentRuns.data?.runs ?? []).length === 0 ? (
                <p className="px-lg py-lg text-[13px] leading-relaxed text-on-ink-faint">
                  Nothing yet. Research a name and the run is recorded here, so you can come
                  back and see what you concluded and why.
                </p>
              ) : (
                recentRuns.data?.runs.map((r) => (
                  <button
                    key={r.run_uid}
                    type="button"
                    onClick={() => navigate(`/plan/${r.ticker}`)}
                    className="flex w-full items-baseline gap-sm border-t border-ink-line px-lg py-sm text-left transition-colors first:border-t-0 hover:bg-ink"
                  >
                    <span className="font-display text-[13px] text-bone">{r.ticker}</span>
                    <span className="font-display text-label uppercase tracking-[0.12em] text-on-ink-faint">
                      {r.mode}
                    </span>
                    {r.output?.stance && (
                      <span className="font-display text-label text-cadmium">
                        {r.output.stance} {r.output.conviction_score ?? ""}
                      </span>
                    )}
                    <span className="ml-auto font-display text-label text-on-ink-faint">
                      {r.created_at?.slice(0, 10)}
                    </span>
                  </button>
                ))
              )}
            </div>

            <div className="border border-ink-line bg-ink-raised">
              <div className="flex items-baseline justify-between border-b border-ink-line px-lg py-sm">
                <h2 className="font-display text-label uppercase tracking-[0.18em] text-on-ink-faint">
                  Recent decisions
                </h2>
                <button
                  type="button"
                  onClick={() => navigate("/decide")}
                  className="font-display text-label uppercase tracking-[0.14em] text-cobalt transition-colors hover:text-cadmium"
                >
                  Decide →
                </button>
              </div>
              {(recentDecisions.data?.decisions ?? []).length === 0 ? (
                <p className="px-lg py-lg text-[13px] leading-relaxed text-on-ink-faint">
                  No calls recorded. Once you record one it appears here with the move since —
                  the point being to check whether the reasoning held, not just the price.
                </p>
              ) : (
                recentDecisions.data?.decisions.map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => navigate(`/decide/${d.ticker}`)}
                    className="flex w-full items-baseline gap-sm border-t border-ink-line px-lg py-sm text-left transition-colors first:border-t-0 hover:bg-ink"
                  >
                    <span className="font-display text-label uppercase tracking-[0.12em] text-on-ink">
                      {d.action}
                    </span>
                    <span className="font-display text-[13px] text-bone">{d.ticker}</span>
                    {d.outcome?.scored && (
                      <span
                        className={`font-display text-label tabular ${
                          (d.outcome.in_your_favour_pct ?? 0) >= 0 ? "text-verdigris" : "text-oxide"
                        }`}
                      >
                        {(d.outcome.in_your_favour_pct ?? 0) >= 0 ? "+" : ""}
                        {(d.outcome.in_your_favour_pct ?? 0).toFixed(1)}%
                      </span>
                    )}
                    <span className="ml-auto font-display text-label text-on-ink-faint">
                      {d.created_at?.slice(0, 10)}
                    </span>
                  </button>
                ))
              )}
            </div>
          </section>


          {/* Watchlist + sector + providers — the working widgets, compact */}
          <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="bg-surface-card rounded-xl p-4 border border-border/60">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Watchlists</p>
              <p className="text-label text-gray-600 mb-3">
                Edit <span className="font-mono text-gray-500">config/watchlists.json</span>
              </p>
              {groupKeys.length > 0 ? (
                <select
                  value={watchGroup}
                  onChange={(e) => setWatchGroup(e.target.value)}
                  className="w-full bg-surface-elevated border border-border rounded-lg px-2 py-1.5 text-sm text-white mb-2"
                >
                  {groupKeys.map((k) => (
                    <option key={k} value={k}>
                      {k} ({watchlists.data![k].length})
                    </option>
                  ))}
                </select>
              ) : (
                <p className="text-sm text-gray-500">Loading…</p>
              )}
              <div className="flex flex-wrap gap-1 max-h-32 overflow-y-auto mt-1">
                {tickers.slice(0, 24).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => navigate(`/research/${t}`)}
                    className="text-label py-0.5 px-1.5 rounded hover:bg-surface-elevated text-gray-300 font-mono border border-border/40"
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            <div id="sectors" className="bg-surface-card rounded-xl p-4 border border-border/60">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-gray-500 uppercase tracking-wider">Sector drift</p>
                <span className="text-label text-gray-600">{sectorLabel}</span>
              </div>
              {sectorData.length > 0 ? (
                sectorData
                  .sort((a, b) => b.change_pct - a.change_pct)
                  .slice(0, 8)
                  .map((s) => (
                    <div key={s.sector} className="flex justify-between py-0.5 text-label">
                      <span className="text-gray-400 truncate mr-2">{s.sector}</span>
                      <span
                        className={`font-mono ${
                          s.change_pct > 0
                            ? "text-accent-green"
                            : s.change_pct < 0
                              ? "text-accent-red"
                              : "text-gray-500"
                        }`}
                      >
                        {s.change_pct > 0 ? "+" : ""}
                        {s.change_pct.toFixed(2)}%
                      </span>
                    </div>
                  ))
              ) : (
                <p className="text-sm text-gray-500">Loading…</p>
              )}
              {sectors.data?.source && (
                <p className="text-label text-gray-600 mt-2">{sectors.data.source}</p>
              )}
            </div>

            <div id="providers" className="bg-surface-card rounded-xl p-4 border border-border/60">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Data providers</p>
              {providers.data ? (
                providers.data.providers.map((p) => (
                  <div key={p.name} className="flex items-center justify-between py-0.5 text-label">
                    <span className="text-gray-400 capitalize truncate mr-2">
                      {p.name}
                    </span>
                    <span
                      className={
                        p.available
                          ? "text-accent-green font-mono"
                          : "text-gray-600 font-mono"
                      }
                    >
                      {p.available ? "active" : "off"}
                    </span>
                  </div>
                ))
              ) : (
                <p className="text-sm text-gray-500">Loading…</p>
              )}
            </div>
          </section>

          {/* Run it locally */}
          <section className="border border-ink-line bg-ink-raised p-lg">
            <h3 className="mb-sm font-display text-label uppercase tracking-[0.18em] text-on-ink-faint">
              Run it locally
            </h3>
            <pre className="overflow-x-auto border border-ink-line bg-ink p-md font-display text-[12px] leading-relaxed text-cadmium">
{`cd ai-hedge-fund
./start.sh                       # API on :8000, UI on :5173
./start.sh --api-port 8010 --ui-port 5174   # if those ports are taken`}
            </pre>
            <p className="mt-sm text-[12px] leading-relaxed text-on-ink-faint">
              For the AI thesis you also need{" "}
              <a
                href="https://ollama.com"
                target="_blank"
                rel="noreferrer"
                className="text-cobalt hover:text-cadmium"
              >
                Ollama
              </a>{" "}
              running with a model pulled —{" "}
              <span className="font-display text-on-ink-soft">ollama pull qwen3:30b</span>.
              Optional extras and API keys live on the{" "}
              <button
                type="button"
                onClick={() => navigate("/setup")}
                className="text-cobalt underline-offset-4 hover:text-cadmium hover:underline"
              >
                setup screen
              </button>
              .
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Sub-components
// ------------------------------------------------------------------

function SnapshotCard({
  label,
  value,
  sub,
  href,
  cta,
}: {
  label: string;
  value: string;
  sub: string;
  href: string;
  cta: string;
}) {
  return (
    <div className="bg-surface-card rounded-xl p-4 border border-border/60">
      <p className="text-label text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className="text-xl font-bold font-mono text-white">{value}</p>
      <p className="text-label text-gray-500 mt-1">{sub}</p>
      {cta && (
        <a
          href={href}
          className="text-label text-blue-400 hover:underline mt-2 inline-block"
        >
          {cta}
        </a>
      )}
    </div>
  );
}

