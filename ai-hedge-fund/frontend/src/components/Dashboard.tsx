import { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { ChatInput } from "./ChatInput";
import { AppNav } from "./AppNav";

export function Dashboard() {
  const navigate = useNavigate();
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
    <div className="flex flex-col h-screen">
      <AppNav
        active="home"
        end={<span className="text-xs text-gray-600 font-mono">Ollama · yfinance · EDGAR · MCP</span>}
      />

      <div className="grow overflow-y-auto">
        <div className="max-w-6xl mx-auto px-6 py-8 flex flex-col gap-8">
          {/* Hero */}
          <section className="flex flex-col gap-3">
            <h1 className="text-3xl font-bold text-white">MJ Research</h1>
            <p className="text-gray-400 text-sm leading-relaxed max-w-2xl">
              A local-first research and portfolio workstation. Multi-provider data,
              AI committee analysis with named-investor lenses, rule-based backtesting,
              portfolio construction (HRP / Markowitz / conviction-weighted), SEC-native
              alt data, and an MCP server so you can drive it all from Claude Desktop.
              No API keys required — Ollama runs the LLM locally.
            </p>
            <div className="max-w-xl mt-1">
              <ChatInput onSubmit={handleSearch} placeholder="Research a ticker (e.g. AAPL, NVDA, 7203.T)" />
            </div>
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

          {/* Feature grid */}
          <section>
            <div className="flex items-baseline justify-between mb-4">
              <h2 className="text-xl font-bold text-white">What's here</h2>
              <p className="text-xs text-gray-500">Every surface is a click away</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FeatureCard
                badge="Phase 1"
                title="Multi-provider market data"
                body="Nine providers orchestrated by priority with fallback, caching, and rate limiting: openbb, yfinance, pandas-datareader, finnhub, Alpha Vantage, Twelve Data, EDGAR, FMP, financial-datasets. Price, fundamentals, technicals, options, earnings, analyst targets, FinBERT news sentiment, ESG, Fama-French 5-factor, FRED macro."
                cta="Open research"
                onClick={() => navigate("/research")}
              />
              <FeatureCard
                badge="Phase 2"
                title="AI research committee"
                body="13 investor personas (Buffett, Graham, Ackman, Cathie Wood, Munger, Burry, Pabrai, Lynch, Fisher, Jhunjhunwala, Druckenmiller, Damodaran, + generic analyst). Run as Committee mode: four personas in parallel via asyncio, then a Portfolio Manager synthesis — 3–4× faster than sequential. Output: conviction (0–100), stance, thesis, bull/bear, named risks."
                cta="Run committee"
                onClick={() => navigate("/research")}
              />
              <FeatureCard
                badge="Phase 2+"
                title="Signal Intelligence"
                body="Post-thesis contrarian callouts: where your AI stance disagrees with sell-side analysts, where it buys pessimism or sells euphoria, unusual news buzz, sector sentiment gaps. Plus committee spread — unanimity vs 3-stance divergence, with guidance on when to verify assumptions."
                cta="See it live"
                onClick={() => navigate("/research/AAPL")}
              />
              <FeatureCard
                badge="Phase 2.5"
                title="Fundamental screeners"
                body="Yartseva Multibagger (hard filters + weighted 6-factor composite, tiered 35–100) and Acquisition Compounder (9-factor score /45, growth + ROIC + FCF conversion + leverage + goodwill heuristic). Watchlist picker, custom universes, live yfinance data."
                cta="Open screeners"
                onClick={() => navigate("/screeners")}
              />
              <FeatureCard
                badge="Phase 3"
                title="Rule-based backtesting"
                body="Six vectorized strategies: Buy & Hold, Golden Cross, RSI Mean Reversion, Bollinger Breakout, Buy-the-Dip in Uptrend, 6-month Momentum. No look-ahead bias (one-bar signal lag), 5 bps per-side fees, full metrics (Sharpe, Sortino, Calmar, max DD, win rate) plus round-trip trade log."
                cta="Open research → Backtest tab"
                onClick={() => navigate("/research/AAPL")}
              />
              <FeatureCard
                badge="Phase 4"
                title="Portfolio construction"
                body="Five allocation methods: Equal Weight, AI Conviction Weighted (< 40 filtered out), Inverse Vol, Markowitz Max-Sharpe (blends conviction with history), and Hierarchical Risk Parity (Lopez de Prado 2016 — robust to estimation error). Per-ticker conviction sliders, donut chart, equity curve vs 1/N benchmark."
                cta="Optimize a basket"
                onClick={() => navigate("/optimize")}
              />
              <FeatureCard
                badge="Phase 5"
                title="EDGAR alt data"
                body="Real SEC filings via EDGAR — 10-K / 10-Q / 8-K / Form 4 / 13F-HR / DEF 14A / SC 13G/D with direct sec.gov links. SIC-classified peer groups (not yfinance sector slop) ranked by market cap. No API key — just set SEC_USER_AGENT."
                cta="Research → Alt data tab"
                onClick={() => navigate("/research/MSFT")}
              />
              <FeatureCard
                badge="Phase 7"
                title="MCP server for Claude Desktop"
                body="The whole stack — research_ticker, get_market_data, get_sec_filings, get_peers, run_backtest, optimize_portfolio, describe_research_graph — exposed as MCP tools. Drop one JSON block into Claude Desktop's config and research any ticker by asking. Also: GET /api/research/graph for the workflow topology."
                cta="See Claude Desktop config"
                onClick={() => window.open("https://github.com/karanmjpinto/ai-hedge-fund#mcp-server-claude-desktop-cursor-etc", "_blank")}
              />
            </div>
          </section>

          {/* Watchlist + sector + providers — the working widgets, compact */}
          <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="bg-surface-card rounded-xl p-4 border border-border/60">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Watchlists</p>
              <p className="text-[11px] text-gray-600 mb-3">
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
                    className="text-[11px] py-0.5 px-1.5 rounded hover:bg-surface-elevated text-gray-300 font-mono border border-border/40"
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            <div id="sectors" className="bg-surface-card rounded-xl p-4 border border-border/60">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-gray-500 uppercase tracking-wider">Sector drift</p>
                <span className="text-[10px] text-gray-600">{sectorLabel}</span>
              </div>
              {sectorData.length > 0 ? (
                sectorData
                  .sort((a, b) => b.change_pct - a.change_pct)
                  .slice(0, 8)
                  .map((s) => (
                    <div key={s.sector} className="flex justify-between py-0.5 text-[11px]">
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
                <p className="text-[10px] text-gray-600 mt-2">{sectors.data.source}</p>
              )}
            </div>

            <div id="providers" className="bg-surface-card rounded-xl p-4 border border-border/60">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Data providers</p>
              {providers.data ? (
                providers.data.providers.map((p) => (
                  <div key={p.name} className="flex items-center justify-between py-0.5 text-[11px]">
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

          {/* How to run section */}
          <section className="bg-surface-card rounded-xl p-5 border border-border/60">
            <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">
              Run it locally
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
              <StepCard
                n="1"
                title="Backend"
                code={`cd ai-hedge-fund
uv run uvicorn hedge_fund.api.main:app --reload`}
              />
              <StepCard
                n="2"
                title="Frontend"
                code={`cd ai-hedge-fund/frontend
npm run dev`}
              />
              <StepCard
                n="3"
                title="Ollama (for AI)"
                code={`ollama pull llama3.2
ollama serve`}
              />
            </div>
            <p className="text-[11px] text-gray-500 mt-3">
              Optional: <span className="font-mono text-gray-400">uv sync --extra sentiment</span>{" "}
              for FinBERT headlines,{" "}
              <span className="font-mono text-gray-400">uv sync --extra openai</span> for hosted LLM,{" "}
              or <span className="font-mono text-gray-400">uv run hedge-fund-mcp</span> to start the
              MCP server for Claude Desktop.
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
      <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className="text-xl font-bold font-mono text-white">{value}</p>
      <p className="text-[11px] text-gray-500 mt-1">{sub}</p>
      {cta && (
        <a
          href={href}
          className="text-[11px] text-blue-400 hover:underline mt-2 inline-block"
        >
          {cta}
        </a>
      )}
    </div>
  );
}

function FeatureCard({
  badge,
  title,
  body,
  cta,
  onClick,
}: {
  badge: string;
  title: string;
  body: string;
  cta: string;
  onClick: () => void;
}) {
  return (
    <div className="bg-surface-card rounded-xl p-5 border border-border/60 flex flex-col gap-3 hover:border-blue-500/40 transition-colors">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono uppercase tracking-wider text-blue-400 bg-blue-500/10 border border-blue-500/30 rounded px-1.5 py-0.5">
          {badge}
        </span>
      </div>
      <h3 className="text-base font-semibold text-white leading-snug">{title}</h3>
      <p className="text-xs text-gray-400 leading-relaxed flex-1">{body}</p>
      <button
        type="button"
        onClick={onClick}
        className="text-xs text-blue-400 hover:text-blue-300 self-start font-medium transition-colors"
      >
        {cta} →
      </button>
    </div>
  );
}

function StepCard({ n, title, code }: { n: string; title: string; code: string }) {
  return (
    <div className="bg-black/30 rounded-lg p-3 border border-border/40">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[10px] font-mono font-bold text-blue-400 bg-blue-500/10 border border-blue-500/30 rounded-full w-5 h-5 flex items-center justify-center">
          {n}
        </span>
        <p className="text-xs font-semibold text-gray-300">{title}</p>
      </div>
      <pre className="text-[11px] font-mono text-gray-400 whitespace-pre-wrap leading-snug">
        {code}
      </pre>
    </div>
  );
}
