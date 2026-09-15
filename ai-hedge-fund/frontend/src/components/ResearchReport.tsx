import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState, useMemo } from "react";
import { useTicker } from "@/lib/ticker-context";
import {
  api,
  type EarningsInfo,
  type AnalystRating,
  type InsiderTransaction,
  type InstitutionalHolder,
  type NewsSentiment,
  type OptionsChain,
  type ResearchCheckResponse,
  type ESGScores,
  type SECFiling,
  type CongressionalTrade,
  type PeerComparison,
  type CommitteeEntry,
  type CommitteeRefinement,
  type Dissent,
  type AiAnalysisBlock,
} from "@/lib/api";
import { ChatInput } from "./ChatInput";
import { ConvictionGauge } from "./ConvictionGauge";
import { PriceChart } from "./PriceChart";
import { AppNav } from "./AppNav";
import { ErrorBoundary } from "./ErrorBoundary";
import { PersonaOpinionGrid, PersonaCard, humanizePersonaId, SynthesisCard } from "./PersonaOpinionCards";
import {
  ResponsiveContainer,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  LineChart,
  Line,
  Legend,
} from "recharts";

const TABS = [
  "Investor views",
  "Fundamental",
  "Technical",
  "Alt data",
  "Peers",
  "Backtest",
  "Sentiment",
  "Macro",
  "Institutional",
] as const;

export function ResearchReport() {
  const { ticker: paramTicker } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get("tab") ?? "Investor views";
  const setActiveTab = (tab: string) => setSearchParams((prev) => { const next = new URLSearchParams(prev); next.set("tab", tab); return next; }, { replace: true });
  const [includeAi, setIncludeAi] = useState(false);
  /** default = generic analyst; committee = multi persona + PM synthesis; persona = one named style */
  const [investorMode, setInvestorMode] = useState<"default" | "committee" | "persona">("committee");
  const [personaId, setPersonaId] = useState("warren_buffett");
  const { ticker: activeTicker, recents } = useTicker();
  const ticker = paramTicker?.toUpperCase() ?? "";

  const personasQuery = useQuery({
    queryKey: ["research-personas"],
    queryFn: () => api.getPersonas(),
    staleTime: 60_000 * 60,
  });

  const research = useQuery({
    queryKey: ["research", ticker, includeAi, investorMode, personaId],
    queryFn: () =>
      api.checkTicker(ticker, {
        includeAi,
        committee: includeAi && investorMode === "committee",
        persona: includeAi && investorMode === "persona" ? personaId : null,
      }),
    enabled: !!ticker,
  });

  const priceData = useQuery({
    queryKey: ["price", ticker],
    queryFn: () => api.getPrice(ticker, 180),
    enabled: !!ticker,
  });

  // Enrichment queries — only fetch when the relevant tab is active
  const earnings = useQuery({
    queryKey: ["earnings", ticker],
    queryFn: () => api.getEarnings(ticker),
    enabled: !!ticker && activeTab === "Fundamental",
    retry: false,
  });

  const analyst = useQuery({
    queryKey: ["analyst", ticker],
    queryFn: () => api.getAnalyst(ticker),
    enabled: !!ticker && activeTab === "Fundamental",
    retry: false,
  });

  const sentiment = useQuery({
    queryKey: ["sentiment", ticker],
    queryFn: () => api.getSentiment(ticker),
    enabled: !!ticker && activeTab === "Sentiment",
    retry: false,
  });

  const newsData = useQuery({
    queryKey: ["news", ticker],
    queryFn: () => api.getNews(ticker, 10),
    enabled: !!ticker && activeTab === "Sentiment",
    retry: false,
  });

  const insider = useQuery({
    queryKey: ["insider", ticker],
    queryFn: () => api.getInsider(ticker),
    enabled: !!ticker && activeTab === "Institutional",
    retry: false,
  });

  const institutional = useQuery({
    queryKey: ["institutional", ticker],
    queryFn: () => api.getInstitutional(ticker),
    enabled: !!ticker && activeTab === "Institutional",
    retry: false,
  });

  const options = useQuery({
    queryKey: ["options", ticker],
    queryFn: () => api.getOptions(ticker),
    enabled: !!ticker && activeTab === "Technical",
    retry: false,
  });

  // Alt Data tab queries
  const esg = useQuery({
    queryKey: ["esg", ticker],
    queryFn: () => api.getESG(ticker),
    enabled: !!ticker && activeTab === "Alt data",
    retry: false,
  });

  const filings = useQuery({
    queryKey: ["filings", ticker],
    queryFn: () => api.getFilings(ticker),
    enabled: !!ticker && activeTab === "Alt data",
    retry: false,
  });

  const congressional = useQuery({
    queryKey: ["congressional", ticker],
    queryFn: () => api.getCongressional(ticker),
    enabled: !!ticker && activeTab === "Alt data",
    retry: false,
  });

  const insiderAlt = useQuery({
    queryKey: ["insider-alt", ticker],
    queryFn: () => api.getInsider(ticker),
    enabled: !!ticker && activeTab === "Alt data",
    retry: false,
  });

  // Peers tab query
  const peers = useQuery({
    queryKey: ["peers", ticker],
    queryFn: () => api.getPeers(ticker),
    enabled: !!ticker && activeTab === "Peers",
    retry: false,
  });

  // Signal Intelligence — pull analyst and sentiment on every tab so the header panel
  // can surface non-consensus callouts as soon as AI thesis is available
  const analystSig = useQuery({
    queryKey: ["analyst-sig", ticker],
    queryFn: () => api.getAnalyst(ticker),
    enabled: !!ticker && includeAi,
    retry: false,
    staleTime: 5 * 60_000,
  });

  const sentimentSig = useQuery({
    queryKey: ["sentiment-sig", ticker],
    queryFn: () => api.getSentiment(ticker),
    enabled: !!ticker && includeAi,
    retry: false,
    staleTime: 5 * 60_000,
  });

  const handleSearch = (query: string) => {
    const t = query.replace(/^check\s+/i, "").trim().toUpperCase();
    if (t) navigate(`/research/${t}`);
  };

  if (!ticker) {
    // Landing here with a name already in flight is common — arriving from the
    // portfolio, or back-navigating. Offer it rather than asking again.
    const resume = activeTicker && activeTicker !== ticker ? activeTicker : null;
    const others: string[] = recents.filter((r: string) => r !== resume).slice(0, 5);
    return (
      <div className="flex h-screen flex-col">
        <AppNav active="research" />
        <div className="flex grow items-center justify-center px-lg">
          <div className="w-full max-w-lg">
            <h1 className="mb-md text-center font-display text-display-sm tracking-tight text-bone">
              Research a ticker
            </h1>
            <ChatInput onSubmit={handleSearch} placeholder="Enter a ticker symbol (e.g. AAPL, THYAO.IS)" />

            {resume && (
              <button
                type="button"
                onClick={() => navigate(`/research/${resume}`)}
                className="mt-md w-full bg-ink-raised px-lg py-md text-left transition-colors hover:bg-ink-line"
              >
                <span className="font-display text-label uppercase tracking-[0.16em] text-on-ink-faint">
                  Pick up where you left off
                </span>
                <span className="mt-2xs block font-display text-[18px] text-cadmium">{resume}</span>
              </button>
            )}

            {others.length > 0 && (
              <div className="mt-md flex flex-wrap items-center gap-2xs">
                <span className="font-display text-label uppercase tracking-[0.16em] text-on-ink-faint">
                  Recent
                </span>
                {others.map((r: string) => (
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
          </div>
        </div>
      </div>
    );
  }

  const d = research.data as ResearchCheckResponse | undefined;
  const fundamentals = (d?.fundamentals ?? {}) as Record<string, unknown>;
  const technicals = (d?.technicals ?? {}) as Record<string, unknown>;
  const ai = d?.ai_full;
  /** Once the AI thesis is on screen the right rail is redundant — the synthesis
   * card already carries conviction and stance, and the extra column only
   * squeezes the analysis. Give the page back to the analysis. */
  const aiResultsShown =
    includeAi && !d?.ai_error && (Boolean(ai) || (d?.committee?.length ?? 0) > 0);

  return (
    <div className="flex flex-col h-screen">
      {/* No search in the end slot: the nav carries one now, and two ticker
          inputs in the same bar is a question about which one is real. The
          full-page search below still stands for the empty state, where
          choosing a company is the whole job. */}
      <AppNav active="research" />

      <div className="flex grow overflow-hidden">
        {/* Main content */}
        <main className="grow p-6 overflow-y-auto flex flex-col gap-6">
          {/* Ticker header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-white">{ticker}</h1>
              <p className="text-gray-400">{fundamentals.name as string ?? ticker}</p>
            </div>
            {d?.price?.current != null && (
              <div className="text-right">
                <p className="text-3xl font-bold text-white font-mono">
                  ${typeof d.price.current === "number" ? d.price.current.toFixed(2) : String(d.price.current)}
                </p>
                <p className={`text-sm font-mono ${(d.price.change_30d_pct ?? 0) >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                  {(d.price.change_30d_pct ?? 0) >= 0 ? "+" : ""}
                  {typeof d.price.change_30d_pct === "number" ? d.price.change_30d_pct.toFixed(2) : d.price.change_30d_pct}% (30d)
                </p>
              </div>
            )}
          </div>

          {/* A button, not a checkbox. This starts a job that takes tens of
           * seconds and costs real compute — a tickbox reads as a passive
           * preference, which is the wrong signal for an action. */}
          <div className="flex flex-wrap items-center gap-sm">
            <button
              type="button"
              onClick={() => setIncludeAi((v) => !v)}
              aria-pressed={includeAi}
              title="Runs locally via Ollama — no API key needed."
              className={`px-5 py-2.5 font-display text-label uppercase tracking-[0.14em] transition-colors ${
                includeAi
                  ? "bg-cadmium text-on-accent hover:bg-oxide hover:text-on-accent-light"
                  : "bg-cobalt text-on-accent-light hover:bg-cadmium hover:text-on-accent"
              }`}
            >
              {includeAi ? "AI thesis on — turn off" : "Run AI thesis"}
            </button>
            <span className="text-xs text-on-ink-faint">
              {includeAi
                ? "Runs on every ticker you open until you turn it off."
                : "Local model, no API key. Takes 10–30 seconds."}
            </span>
          </div>

          {includeAi && (
            <div className="flex flex-col gap-2 p-4 rounded-xl bg-surface-card/50 border border-border/60">
              <p className="text-xs text-gray-500 uppercase tracking-wider">Investor lens</p>
              <div className="flex flex-wrap gap-2">
                {(
                  [
                    ["committee", "Committee"],
                    ["persona", "Single investor"],
                    ["default", "Generic analyst"],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setInvestorMode(id)}
                    className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                      investorMode === id
                        ? "bg-blue-500/25 text-blue-300 border border-blue-500/40"
                        : "text-gray-500 border border-transparent hover:bg-surface-card hover:text-gray-300"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {investorMode === "persona" && (
                <select
                  aria-label="Investor persona style"
                  value={personaId}
                  onChange={(e) => setPersonaId(e.target.value)}
                  className="mt-1 bg-surface-elevated border border-border rounded-lg px-3 py-2 text-sm text-white max-w-md"
                >
                  {(personasQuery.data?.personas ?? [])
                    .filter((p) => p.id !== "default")
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {humanizePersonaId(p.id)}
                      </option>
                    ))}
                </select>
              )}
              {investorMode === "committee" && (
                <p className="text-xs text-gray-500">
                  Runs each selected style on the same data, then a portfolio-manager synthesis. Open the{" "}
                  <strong className="text-gray-400">Investor views</strong> tab for per-investor cards.
                </p>
              )}
            </div>
          )}

          {includeAi && d?.ai_error && (
            <div className="bg-amber-900/30 border border-amber-700/50 rounded-lg p-3 text-sm text-amber-200">
              AI unavailable: {(d.ai_error as { message?: string }).message ?? d.ai_error.error}
            </div>
          )}

          {/* Quick stance strip — committee only */}
          {includeAi && investorMode === "committee" && d?.committee && d.committee.length > 0 && (
            <div className="flex flex-wrap gap-2 items-center">
              <span className="text-xs text-gray-500 mr-1">Snapshot:</span>
              {d.committee.map((c, i) => {
                const st = c.analysis?.stance ?? "—";
                const col =
                  st === "BUY"
                    ? "text-emerald-400 border-emerald-500/30"
                    : st === "SELL"
                      ? "text-red-400 border-red-500/30"
                      : "text-amber-400 border-amber-500/30";
                return (
                  <span
                    key={`${c.persona_id}-${i}`}
                    className={`text-label px-2 py-1 rounded-md border bg-black/20 ${col}`}
                  >
                    {humanizePersonaId(c.persona_id)}: {st}
                  </span>
                );
              })}
            </div>
          )}

          {includeAi && ai && investorMode !== "committee" && (
            <div className="flex flex-col gap-4">
              <div className="grid md:grid-cols-2 gap-4">
                <div className="bg-surface-card rounded-xl p-4">
                  <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-2">
                    Investment thesis
                    {d?.persona_id && (
                      <span className="ml-2 text-blue-400 normal-case">
                        ({humanizePersonaId(d.persona_id)})
                      </span>
                    )}
                  </h3>
                  <p className="text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">
                    {ai.investment_thesis}
                  </p>
                </div>
                <div className="grid grid-cols-1 gap-3">
                  <div className="bg-surface-card rounded-xl p-4">
                    <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-2">Bull case</h3>
                    <p className="text-sm text-gray-300 whitespace-pre-wrap">{ai.bull_case}</p>
                  </div>
                  <div className="bg-surface-card rounded-xl p-4">
                    <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-2">Bear case</h3>
                    <p className="text-sm text-gray-300 whitespace-pre-wrap">{ai.bear_case}</p>
                  </div>
                </div>
              </div>
              {ai.key_risks?.length > 0 && (
                <div className="bg-surface-card rounded-xl p-4">
                  <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-2">Key risks</h3>
                  <ul className="list-disc list-inside text-sm text-gray-300 space-y-1">
                    {ai.key_risks.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}
              {d.evaluation && (
                <div className="text-xs text-gray-600 font-mono bg-surface-elevated rounded p-2">
                  Evaluation: {JSON.stringify(d.evaluation)}
                  {d.ai_model && ` · model ${d.ai_model}`}
                </div>
              )}
            </div>
          )}

          {includeAi && ai && investorMode === "committee" && (
            <div className="flex flex-col gap-4">
              <SynthesisCard analysis={ai} />
              {d.evaluation && (
                <div className="text-xs text-gray-600 font-mono bg-surface-elevated rounded p-2">
                  Evaluation: {JSON.stringify(d.evaluation)}
                  {d.ai_model && ` · model ${d.ai_model}`}
                </div>
              )}
            </div>
          )}

          {/* Signal Intelligence — only after AI thesis is run */}
          {includeAi && ai && !d?.ai_error && (
            <SignalIntelligence
              ai={ai}
              committee={d?.committee ?? null}
              refinement={d?.refinement ?? null}
              dissent={d?.dissent ?? null}
              analyst={analystSig.data ?? null}
              sentiment={sentimentSig.data ?? null}
              newsSentimentMean={d?.news_sentiment?.enabled ? d.news_sentiment.aggregate.mean_signed : null}
            />
          )}

          {/* Tabs */}
          <div className="flex gap-1 border-b border-border">
            {TABS.map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab
                    ? "text-blue-400 border-blue-400"
                    : "text-gray-500 border-transparent hover:text-gray-300"
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Chart */}
          <div className="bg-surface-card rounded-xl p-4 h-72">
            <PriceChart data={priceData.data?.data ?? []} loading={priceData.isLoading} />
          </div>

          <ErrorBoundary>
          {/* ================================================================ */}
          {/* INVESTOR VIEWS TAB */}
          {/* ================================================================ */}
          {activeTab === "Investor views" && (
            <div className="flex flex-col gap-4">
              {!includeAi && (
                <div className="bg-surface-card rounded-xl p-8 text-center border border-dashed border-border">
                  <p className="text-gray-400 text-sm">
                    Press <strong className="text-bone">Run AI thesis</strong> above, then choose{" "}
                    <strong className="text-bone">Committee</strong> or{" "}
                    <strong className="text-bone">Single investor</strong> to see named investor
                    takes on this symbol.
                  </p>
                </div>
              )}
              {includeAi && d?.ai_error && (
                <div className="bg-amber-900/20 border border-amber-700/40 rounded-xl p-4 text-sm text-amber-200">
                  Fix the error above to load investor views.
                </div>
              )}
              {includeAi && !d?.ai_error && investorMode === "committee" && d?.committee && d.committee.length > 0 && (
                <PersonaOpinionGrid
                  committee={d.committee}
                  committeeRound1={d.committee_round1 ?? null}
                  synthesisAnalysis={ai ?? undefined}
                  showSynthesisFirst={false}
                />
              )}
              {includeAi && !d?.ai_error && investorMode === "persona" && ai && (
                <div className="max-w-3xl">
                  <PersonaCard
                    entry={{
                      persona_id: d?.persona_id ?? personaId,
                      analysis: ai,
                    }}
                    accentIndex={0}
                  />
                </div>
              )}
              {includeAi && !d?.ai_error && investorMode === "default" && ai && (
                <div className="max-w-3xl">
                  <div className="rounded-xl border border-slate-500/30 bg-gradient-to-br from-slate-500/15 to-transparent p-5">
                    <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Generic analyst</p>
                    <p className="text-sm text-gray-100 whitespace-pre-wrap leading-relaxed">{ai.investment_thesis}</p>
                    <div className="grid md:grid-cols-2 gap-3 mt-4 text-xs text-gray-400">
                      <p>
                        <span className="text-emerald-500/90">Bull:</span> {ai.bull_case}
                      </p>
                      <p>
                        <span className="text-red-400/90">Bear:</span> {ai.bear_case}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ================================================================ */}
          {/* FUNDAMENTAL TAB */}
          {/* ================================================================ */}
          {activeTab === "Fundamental" && (
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-3 gap-4">
                <DataCard title="Key Metrics" items={[
                  ["P/E Ratio", fundamentals.pe_ratio != null ? (fundamentals.pe_ratio as number).toFixed(2) : "N/A"],
                  ["Forward P/E", fundamentals.forward_pe != null ? (fundamentals.forward_pe as number).toFixed(2) : "N/A"],
                  ["PEG Ratio", fundamentals.peg_ratio != null ? (fundamentals.peg_ratio as number).toFixed(2) : "N/A"],
                  ["P/B Ratio", fundamentals.price_to_book != null ? (fundamentals.price_to_book as number).toFixed(2) : "N/A"],
                  ["Div Yield", fundamentals.dividend_yield != null ? `${((fundamentals.dividend_yield as number) * 100).toFixed(2)}%` : "N/A"],
                  ["Beta", fundamentals.beta != null ? (fundamentals.beta as number).toFixed(2) : "N/A"],
                  ["Market Cap", fundamentals.market_cap != null ? `$${((fundamentals.market_cap as number) / 1e9).toFixed(1)}B` : "N/A"],
                ]} />
                <DataCard title="Financials" items={[
                  ["Revenue", fmtLarge(fundamentals.revenue as number)],
                  ["Net Income", fmtLarge(fundamentals.net_income as number)],
                  ["EBITDA", fmtLarge(fundamentals.ebitda as number)],
                  ["FCF", fmtLarge(fundamentals.free_cash_flow as number)],
                  ["Total Assets", fmtLarge(fundamentals.total_assets as number)],
                  ["Total Debt", fmtLarge(fundamentals.total_debt as number)],
                ]} />
                <DataCard title="Price Range" items={[
                  ["Current", d?.price?.current != null ? `$${(d.price.current as number).toFixed(2)}` : "N/A"],
                  ["52w High", fundamentals["52w_high"] != null ? `$${(fundamentals["52w_high"] as number).toFixed(2)}` : "N/A"],
                  ["52w Low", fundamentals["52w_low"] != null ? `$${(fundamentals["52w_low"] as number).toFixed(2)}` : "N/A"],
                  ["30d Change", d?.price?.change_30d_pct != null ? `${(d.price.change_30d_pct as number).toFixed(2)}%` : "N/A"],
                ]} />
              </div>

              {/* Analyst Ratings */}
              {analyst.data && <AnalystCard data={analyst.data} />}

              {/* Earnings */}
              {earnings.data && <EarningsCard data={earnings.data} />}
            </div>
          )}

          {/* ================================================================ */}
          {/* TECHNICAL TAB */}
          {/* ================================================================ */}
          {activeTab === "Technical" && (
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-3 gap-4">
                <DataCard title="Momentum" items={[
                  ["RSI (14)", technicals.rsi_14],
                  ["MACD Trend", (technicals.macd as Record<string, unknown>)?.trend ?? "N/A"],
                  ["MACD Line", (technicals.macd as Record<string, unknown>)?.line],
                  ["MACD Signal", (technicals.macd as Record<string, unknown>)?.signal],
                  ["MACD Hist", (technicals.macd as Record<string, unknown>)?.histogram],
                ]} />
                <DataCard title="Moving Averages" items={[
                  ["SMA 50", technicals.sma_50],
                  ["SMA 200", technicals.sma_200],
                  ["Above SMA50", technicals.above_sma50 != null ? (technicals.above_sma50 ? "Yes" : "No") : "N/A"],
                  ["Above SMA200", technicals.above_sma200 != null ? (technicals.above_sma200 ? "Yes" : "No") : "N/A"],
                ]} />
                <DataCard title="Volatility" items={[
                  ["ATR (14)", technicals.atr_14],
                  ["BB Upper", (technicals.bollinger as Record<string, unknown>)?.upper],
                  ["BB Middle", (technicals.bollinger as Record<string, unknown>)?.middle],
                  ["BB Lower", (technicals.bollinger as Record<string, unknown>)?.lower],
                  ["BB Width %", (technicals.bollinger as Record<string, unknown>)?.width],
                ]} />
              </div>

              {/* Options summary */}
              {options.data && <OptionsCard data={options.data} />}
            </div>
          )}

          {/* ================================================================ */}
          {/* ALT DATA TAB — niche / non-consensus signals */}
          {/* ================================================================ */}
          {activeTab === "Alt data" && (
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <InsiderFlowCard data={insiderAlt.data?.transactions ?? []} loading={insiderAlt.isLoading} />
                <CongressionalCard data={congressional.data?.trades ?? []} loading={congressional.isLoading} />
                <ESGCard data={esg.data ?? null} loading={esg.isLoading} />
              </div>
              <FilingsCard data={filings.data?.filings ?? []} loading={filings.isLoading} />
              {!esg.data && !filings.data?.filings?.length && !congressional.data?.trades?.length &&
                !insiderAlt.data?.transactions?.length && !insiderAlt.isLoading && !filings.isLoading && (
                  <EmptyState message="Alt data loading — set FINNHUB_API_KEY for ESG, congressional trades, and deeper SEC filings." />
                )}
            </div>
          )}

          {/* ================================================================ */}
          {/* PEERS TAB — comparative analysis */}
          {/* ================================================================ */}
          {activeTab === "Peers" && (
            <div className="flex flex-col gap-4">
              {peers.isLoading && <EmptyState message="Loading peers…" />}
              {peers.data && <PeersTab data={peers.data} currentTicker={ticker} />}
              {!peers.isLoading && !peers.data && (
                <EmptyState message="Peer comparison unavailable for this symbol." />
              )}
            </div>
          )}

          {/* ================================================================ */}
          {/* BACKTEST TAB — strategy over historical price series */}
          {/* ================================================================ */}
          {activeTab === "Backtest" && <BacktestTab ticker={ticker} />}

          {/* ================================================================ */}
          {/* SENTIMENT TAB */}
          {/* ================================================================ */}
          {activeTab === "Sentiment" && (
            <div className="flex flex-col gap-4">
              {sentiment.data && <SentimentCard data={sentiment.data} />}

              {/* News list */}
              {newsData.data?.articles && newsData.data.articles.length > 0 && (
                <div className="bg-surface-card rounded-xl p-4">
                  <h3 className="text-white font-semibold mb-3">Recent News</h3>
                  {newsData.data.articles.map((n: Record<string, unknown>, i: number) => (
                    <div key={i} className="py-2 border-t border-border first:border-0">
                      <p className="text-sm text-gray-300">{n.title as string}</p>
                      <div className="flex justify-between mt-1">
                        <p className="text-xs text-gray-600">{n.publisher as string}</p>
                        <p className="text-xs text-gray-600">{n.source as string}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {!sentiment.data && !newsData.data?.articles?.length && (
                <EmptyState message="No sentiment data available. Add a FINNHUB_API_KEY for sentiment scores." />
              )}
            </div>
          )}

          {/* ================================================================ */}
          {/* MACRO TAB */}
          {/* ================================================================ */}
          {activeTab === "Macro" && (
            <div className="flex flex-col gap-4">
              <MacroTab />
            </div>
          )}

          {/* ================================================================ */}
          {/* INSTITUTIONAL TAB */}
          {/* ================================================================ */}
          {activeTab === "Institutional" && (
            <div className="flex flex-col gap-4">
              {institutional.data && <InstitutionalCard data={institutional.data.holders} />}
              {insider.data && <InsiderCard data={insider.data.transactions} />}

              {!institutional.data && !insider.data && (
                <EmptyState message="Loading institutional data..." />
              )}
            </div>
          )}

          {/* Legacy news — show on Fundamental tab */}
          {activeTab === "Fundamental" && d?.news && d.news.length > 0 && (
            <div className="bg-surface-card rounded-xl p-4">
              <h3 className="text-white font-semibold mb-3">Recent News</h3>
              {d.news.map((n, i) => (
                <div key={i} className="py-2 border-t border-border first:border-0">
                  <p className="text-sm text-gray-300">{n.title}</p>
                  <div className="flex justify-between items-center mt-1 gap-2">
                    <p className="text-xs text-gray-600">{n.date}</p>
                    {n.sentiment_label != null && (
                      <span
                        className={`text-xs font-mono shrink-0 ${
                          String(n.sentiment_label).toLowerCase().includes("pos")
                            ? "text-accent-green"
                            : String(n.sentiment_label).toLowerCase().includes("neg")
                              ? "text-accent-red"
                              : "text-gray-400"
                        }`}
                      >
                        {n.sentiment_label}
                        {n.sentiment_score != null ? ` ${(n.sentiment_score as number).toFixed(2)}` : ""}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          </ErrorBoundary>
        </main>

        {/* Right sidebar — hidden once the AI analysis is showing */}
        {!aiResultsShown && (
          <aside className="w-72 shrink-0 border-l border-border p-4 overflow-y-auto flex flex-col gap-4">
            <ConvictionGauge
              score={d?.conviction ?? null}
              label={d?.stance ?? undefined}
            />
            <div className="bg-surface-card rounded-xl p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Sector</p>
              <p className="text-sm text-white">{fundamentals.sector as string ?? "N/A"}</p>
              <p className="text-xs text-gray-500 mt-1">{fundamentals.industry as string ?? ""}</p>
            </div>
            <div className="bg-surface-card rounded-xl p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Exchange</p>
              <p className="text-sm text-white">{fundamentals.exchange as string ?? "N/A"}</p>
              <p className="text-xs text-gray-500 mt-1">{fundamentals.currency as string ?? "USD"}</p>
            </div>
            {d?.news_sentiment && (
              <div className="bg-surface-card rounded-xl p-4">
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Headline sentiment (FinBERT)</p>
                {d.news_sentiment.enabled ? (
                  <>
                    <p className="text-lg font-bold text-white font-mono">
                      {d.news_sentiment.aggregate.mean_signed != null
                        ? d.news_sentiment.aggregate.mean_signed.toFixed(2)
                        : "—"}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      mean signed · {d.news_sentiment.aggregate.article_count} headlines
                    </p>
                    <p className="text-label text-gray-600 mt-2 truncate" title={d.news_sentiment.model ?? ""}>
                      {d.news_sentiment.model ?? "model"}
                    </p>
                  </>
                ) : (
                  <p className="text-xs text-gray-500">
                    {d.news_sentiment.reason === "transformers_not_installed"
                      ? "Not installed — enable with --extra sentiment"
                      : d.news_sentiment.reason ?? "Off"}
                  </p>
                )}
              </div>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Sub-components
// ------------------------------------------------------------------

function DataCard({ title, items }: { title: string; items: [string, unknown][] }) {
  return (
    <div className="bg-surface-card rounded-xl p-4">
      <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">{title}</h3>
      {items.map(([label, value]) => (
        <div key={label} className="flex justify-between py-1 text-sm">
          <span className="text-gray-400">{label}</span>
          <span className="text-white font-mono">{value != null ? String(value) : "N/A"}</span>
        </div>
      ))}
    </div>
  );
}

function AnalystCard({ data }: { data: AnalystRating }) {
  return (
    <div className="bg-surface-card rounded-xl p-4">
      <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">Analyst Consensus</h3>
      <div className="grid grid-cols-4 gap-4 mb-4">
        <div>
          <p className="text-xs text-gray-500">Recommendation</p>
          <p className="text-lg font-bold text-white capitalize">{data.recommendation ?? "N/A"}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Target (Mean)</p>
          <p className="text-lg font-bold text-white font-mono">{data.target_mean ? `$${data.target_mean}` : "N/A"}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Upside</p>
          <p className={`text-lg font-bold font-mono ${(data.upside_pct ?? 0) >= 0 ? "text-accent-green" : "text-accent-red"}`}>
            {data.upside_pct != null ? `${data.upside_pct > 0 ? "+" : ""}${data.upside_pct}%` : "N/A"}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Analysts</p>
          <p className="text-lg font-bold text-white font-mono">{data.num_analysts ?? "N/A"}</p>
        </div>
      </div>
      <div className="flex gap-2 text-xs">
        <span className="text-gray-500">Low: ${data.target_low ?? "?"}</span>
        <span className="text-gray-500">Med: ${data.target_median ?? "?"}</span>
        <span className="text-gray-500">High: ${data.target_high ?? "?"}</span>
      </div>
      {data.recommendation_history?.length > 0 && (
        <div className="mt-3 border-t border-border pt-3">
          <p className="text-xs text-gray-500 mb-2">Recent Ratings</p>
          {data.recommendation_history.slice(0, 5).map((r, i) => (
            <div key={i} className="flex justify-between text-xs py-0.5">
              <span className="text-gray-400">{r.firm}</span>
              <span className="text-white">{r.grade}</span>
              <span className="text-gray-600">{r.date}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function EarningsCard({ data }: { data: EarningsInfo }) {
  return (
    <div className="bg-surface-card rounded-xl p-4">
      <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">Earnings</h3>
      {data.next_earnings_date && (
        <p className="text-sm text-blue-400 mb-3">Next earnings: {data.next_earnings_date}</p>
      )}
      {data.earnings_dates?.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 border-b border-border">
                <th className="text-left py-1">Date</th>
                <th className="text-right py-1">EPS Est</th>
                <th className="text-right py-1">EPS Actual</th>
                <th className="text-right py-1">Surprise</th>
              </tr>
            </thead>
            <tbody>
              {data.earnings_dates.slice(0, 6).map((e, i) => (
                <tr key={i} className="border-b border-border/50">
                  <td className="text-gray-400 py-1">{e.date}</td>
                  <td className="text-right text-gray-300 font-mono">{e.eps_estimate ?? "N/A"}</td>
                  <td className="text-right text-white font-mono">{e.reported_eps ?? "N/A"}</td>
                  <td className={`text-right font-mono ${(e.surprise_pct ?? 0) >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                    {e.surprise_pct != null ? `${e.surprise_pct}%` : "N/A"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SentimentCard({ data }: { data: NewsSentiment }) {
  return (
    <div className="bg-surface-card rounded-xl p-4">
      <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">Sentiment Scores</h3>
      <div className="grid grid-cols-3 gap-4">
        <div>
          <p className="text-xs text-gray-500">Bullish</p>
          <p className="text-lg font-bold text-accent-green font-mono">
            {data.bullish_pct != null ? `${(data.bullish_pct * 100).toFixed(0)}%` : "N/A"}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Bearish</p>
          <p className="text-lg font-bold text-accent-red font-mono">
            {data.bearish_pct != null ? `${(data.bearish_pct * 100).toFixed(0)}%` : "N/A"}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">News Score</p>
          <p className="text-lg font-bold text-white font-mono">
            {data.company_news_score != null ? data.company_news_score.toFixed(2) : "N/A"}
          </p>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div className="flex justify-between">
          <span className="text-gray-500">Buzz Score</span>
          <span className="text-white font-mono">{data.buzz_score ?? "N/A"}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Articles/Week</span>
          <span className="text-white font-mono">{data.articles_in_last_week ?? "N/A"}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Sector Avg Bullish</span>
          <span className="text-white font-mono">
            {data.sector_avg_bullish != null ? `${(data.sector_avg_bullish * 100).toFixed(0)}%` : "N/A"}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Weekly Average</span>
          <span className="text-white font-mono">{data.weekly_average ?? "N/A"}</span>
        </div>
      </div>
    </div>
  );
}

function InsiderCard({ data }: { data: InsiderTransaction[] }) {
  if (!data || data.length === 0) return null;
  return (
    <div className="bg-surface-card rounded-xl p-4">
      <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">Insider Transactions</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-border">
              <th className="text-left py-1">Name</th>
              <th className="text-left py-1">Type</th>
              <th className="text-right py-1">Shares</th>
              <th className="text-right py-1">Value</th>
              <th className="text-right py-1">Date</th>
            </tr>
          </thead>
          <tbody>
            {data.slice(0, 10).map((t, i) => (
              <tr key={i} className="border-b border-border/50">
                <td className="text-gray-300 py-1">{t.name}</td>
                <td className={`py-1 ${t.transaction_type.toLowerCase().includes("sale") ? "text-accent-red" : "text-accent-green"}`}>
                  {t.transaction_type}
                </td>
                <td className="text-right text-white font-mono">{t.shares?.toLocaleString()}</td>
                <td className="text-right text-white font-mono">{t.value ? `$${t.value.toLocaleString()}` : "N/A"}</td>
                <td className="text-right text-gray-500">{t.date ?? "N/A"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function InstitutionalCard({ data }: { data: InstitutionalHolder[] }) {
  if (!data || data.length === 0) return null;
  return (
    <div className="bg-surface-card rounded-xl p-4">
      <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">Top Institutional Holders</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-border">
              <th className="text-left py-1">Holder</th>
              <th className="text-right py-1">Shares</th>
              <th className="text-right py-1">Value</th>
              <th className="text-right py-1">% Out</th>
            </tr>
          </thead>
          <tbody>
            {data.slice(0, 10).map((h, i) => (
              <tr key={i} className="border-b border-border/50">
                <td className="text-gray-300 py-1">{h.holder}</td>
                <td className="text-right text-white font-mono">{h.shares?.toLocaleString()}</td>
                <td className="text-right text-white font-mono">{h.value ? `$${(h.value / 1e6).toFixed(0)}M` : "N/A"}</td>
                <td className="text-right text-white font-mono">{h.pct_held != null ? `${(h.pct_held * 100).toFixed(2)}%` : "N/A"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function OptionsCard({ data }: { data: OptionsChain }) {
  if (!data.expirations?.length) return null;
  return (
    <div className="bg-surface-card rounded-xl p-4">
      <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">Options (nearest expiration: {data.expirations[0]})</h3>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-xs text-gray-500 mb-1">Calls ({data.calls?.length ?? 0})</p>
          {data.calls?.slice(0, 5).map((c: Record<string, unknown>, i: number) => (
            <div key={i} className="flex justify-between text-xs py-0.5">
              <span className="text-gray-400">Strike ${c.strike as number}</span>
              <span className="text-white font-mono">${(c.lastPrice as number)?.toFixed(2) ?? "N/A"}</span>
              <span className="text-gray-500">Vol: {c.volume as number ?? 0}</span>
            </div>
          ))}
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-1">Puts ({data.puts?.length ?? 0})</p>
          {data.puts?.slice(0, 5).map((p: Record<string, unknown>, i: number) => (
            <div key={i} className="flex justify-between text-xs py-0.5">
              <span className="text-gray-400">Strike ${p.strike as number}</span>
              <span className="text-white font-mono">${(p.lastPrice as number)?.toFixed(2) ?? "N/A"}</span>
              <span className="text-gray-500">Vol: {p.volume as number ?? 0}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const FRED_SERIES: { id: string; label: string; unit?: string }[] = [
  { id: "DFF", label: "Fed Funds Rate", unit: "%" },
  { id: "T10Y2Y", label: "10Y-2Y Spread", unit: "%" },
  { id: "UNRATE", label: "Unemployment", unit: "%" },
  { id: "CPIAUCSL", label: "CPI (All Urban)", unit: "idx" },
  { id: "GDP", label: "Nominal GDP", unit: "$B" },
  { id: "DGS10", label: "10Y Treasury Yield", unit: "%" },
  { id: "VIXCLS", label: "VIX", unit: "idx" },
  { id: "M2SL", label: "M2 Money Supply", unit: "$B" },
];

function MacroTab() {
  const [series, setSeries] = useState(FRED_SERIES[0]!.id);

  const famaFrench = useQuery({
    queryKey: ["fama-french"],
    queryFn: () => api.getFamaFrench(),
    retry: false,
  });

  const macro = useQuery({
    queryKey: ["macro", series],
    queryFn: () => api.getMacro(series, 1825),
    retry: false,
  });

  // Build factor averages over recent window (last 24m) for the radar
  const factorAverages = useMemo(() => {
    if (!famaFrench.data?.factors?.length) return [];
    const recent = famaFrench.data.factors.slice(-24);
    const keys = ["Mkt-RF", "SMB", "HML", "RMW", "CMA"] as const;
    return keys.map((k) => ({
      factor: k,
      mean: recent.reduce((acc, f) => acc + (Number(f[k]) || 0), 0) / recent.length,
    }));
  }, [famaFrench.data]);

  const macroSeries = useMemo(() => {
    const rows = macro.data?.data ?? [];
    return rows
      .map((r) => ({
        date: String(r.date ?? r.Date ?? r.DATE ?? ""),
        value: Number((r.value ?? r[series] ?? r[series.toUpperCase()]) ?? NaN),
      }))
      .filter((r) => r.date && !Number.isNaN(r.value));
  }, [macro.data, series]);

  const seriesLabel = FRED_SERIES.find((s) => s.id === series)?.label ?? series;

  return (
    <>
      {/* FRED series picker + chart */}
      <div className="bg-surface-card rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs text-gray-500 uppercase tracking-wider">FRED macro series</h3>
          <select
            value={series}
            onChange={(e) => setSeries(e.target.value)}
            className="bg-surface-elevated border border-border rounded px-2 py-1 text-xs text-white"
            aria-label="FRED series"
          >
            {FRED_SERIES.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label} ({s.id})
              </option>
            ))}
          </select>
        </div>
        {macro.isLoading && <p className="text-sm text-gray-500">Loading {seriesLabel}…</p>}
        {macro.isError && <p className="text-sm text-amber-300">Macro unavailable: {(macro.error as Error).message}</p>}
        {macroSeries.length > 0 && (
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={macroSeries} margin={{ top: 5, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis dataKey="date" tick={{ fill: "#71717a", fontSize: 10 }} minTickGap={40} />
                <YAxis tick={{ fill: "#71717a", fontSize: 10 }} width={50} />
                <Tooltip
                  contentStyle={{ background: "#0b0b0b", border: "1px solid #27272a", fontSize: 12 }}
                  labelStyle={{ color: "#a1a1aa" }}
                />
                <Line type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        <p className="text-label text-gray-600 mt-2">
          Data: FRED via pandas-datareader · 5y window · change series from the dropdown to explore rates, inflation,
          growth, and liquidity.
        </p>
      </div>

      {/* Fama-French radar */}
      {factorAverages.length > 0 && (
        <div className="bg-surface-card rounded-xl p-4">
          <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">
            Fama-French 5-factor · trailing 24m mean ({famaFrench.data?.period ?? "monthly"})
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={factorAverages}>
                  <PolarGrid stroke="#3f3f46" />
                  <PolarAngleAxis dataKey="factor" tick={{ fill: "#a1a1aa", fontSize: 11 }} />
                  <PolarRadiusAxis tick={{ fill: "#52525b", fontSize: 9 }} />
                  <Radar dataKey="mean" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.3} />
                  <Tooltip
                    contentStyle={{ background: "#0b0b0b", border: "1px solid #27272a", fontSize: 12 }}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
            <div className="text-xs text-gray-400 space-y-2">
              <p>
                <span className="text-gray-500 uppercase tracking-wider text-label">Mkt-RF</span> — Excess market return.
                Positive = risk-on backdrop.
              </p>
              <p>
                <span className="text-gray-500 uppercase tracking-wider text-label">SMB</span> — Small-minus-big. Positive
                = small caps outperforming.
              </p>
              <p>
                <span className="text-gray-500 uppercase tracking-wider text-label">HML</span> — High-minus-low book/mkt.
                Positive = value regime.
              </p>
              <p>
                <span className="text-gray-500 uppercase tracking-wider text-label">RMW</span> — Robust-minus-weak profits.
                Positive = quality bid.
              </p>
              <p>
                <span className="text-gray-500 uppercase tracking-wider text-label">CMA</span> — Conservative-minus-aggressive
                investment. Positive = capital-discipline bid.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Fama-French monthly table — last 12 */}
      {famaFrench.data && (
        <div className="bg-surface-card rounded-xl p-4">
          <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">
            Factor returns · last 12 periods
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-border">
                  <th className="text-left py-1">Date</th>
                  <th className="text-right py-1">Mkt-RF</th>
                  <th className="text-right py-1">SMB</th>
                  <th className="text-right py-1">HML</th>
                  <th className="text-right py-1">RMW</th>
                  <th className="text-right py-1">CMA</th>
                  <th className="text-right py-1">RF</th>
                </tr>
              </thead>
              <tbody>
                {famaFrench.data.factors.slice(-12).map((f, i) => (
                  <tr key={i} className="border-b border-border/50">
                    <td className="text-gray-400 py-1">{f.date}</td>
                    <td className={`text-right font-mono ${f["Mkt-RF"] >= 0 ? "text-accent-green" : "text-accent-red"}`}>{f["Mkt-RF"]}</td>
                    <td className={`text-right font-mono ${f.SMB >= 0 ? "text-accent-green" : "text-accent-red"}`}>{f.SMB}</td>
                    <td className={`text-right font-mono ${f.HML >= 0 ? "text-accent-green" : "text-accent-red"}`}>{f.HML}</td>
                    <td className={`text-right font-mono ${f.RMW >= 0 ? "text-accent-green" : "text-accent-red"}`}>{f.RMW}</td>
                    <td className={`text-right font-mono ${f.CMA >= 0 ? "text-accent-green" : "text-accent-red"}`}>{f.CMA}</td>
                    <td className="text-right text-white font-mono">{f.RF}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

// ------------------------------------------------------------------
// Signal Intelligence — non-consensus callouts + committee spread
// ------------------------------------------------------------------

type Callout = {
  kind: "align" | "conflict" | "edge";
  title: string;
  detail: string;
};

function buildCallouts({
  ai,
  analyst,
  sentiment,
  newsSentimentMean,
}: {
  ai: AiAnalysisBlock;
  analyst: AnalystRating | null;
  sentiment: NewsSentiment | null;
  newsSentimentMean: number | null | undefined;
}): Callout[] {
  const out: Callout[] = [];
  const aiBullish = ai.stance === "BUY";
  const aiBearish = ai.stance === "SELL";

  // AI vs analyst consensus
  if (analyst?.upside_pct != null) {
    const analystBullish = analyst.upside_pct > 10;
    const analystBearish = analyst.upside_pct < -5;
    if (aiBullish && analystBearish) {
      out.push({
        kind: "edge",
        title: "Contrarian to analysts",
        detail: `AI is BUY but sell-side targets imply ${analyst.upside_pct.toFixed(1)}% downside — potential edge if thesis is right.`,
      });
    } else if (aiBearish && analystBullish) {
      out.push({
        kind: "edge",
        title: "Ahead of analyst revisions",
        detail: `AI is SELL while sell-side still sees ${analyst.upside_pct.toFixed(1)}% upside — downgrade cycle may be ahead.`,
      });
    } else if (aiBullish && analystBullish) {
      out.push({
        kind: "align",
        title: "Analysts agree",
        detail: `AI BUY stance lines up with ${analyst.upside_pct.toFixed(1)}% consensus upside.`,
      });
    }
  }

  // AI vs news sentiment
  if (typeof newsSentimentMean === "number") {
    if (aiBullish && newsSentimentMean < -0.15) {
      out.push({
        kind: "edge",
        title: "Buying the pessimism",
        detail: `AI BUY while headline sentiment is ${newsSentimentMean.toFixed(2)} (negative) — classic contrarian setup.`,
      });
    } else if (aiBearish && newsSentimentMean > 0.2) {
      out.push({
        kind: "edge",
        title: "Selling the euphoria",
        detail: `AI SELL while news sentiment is ${newsSentimentMean.toFixed(2)} (euphoric) — fading the crowd.`,
      });
    }
  }

  // Sentiment / buzz alt signals
  if (sentiment?.buzz_score != null && sentiment.buzz_score > 1.5) {
    out.push({
      kind: "edge",
      title: "Unusual buzz",
      detail: `Buzz score ${sentiment.buzz_score.toFixed(2)} vs weekly avg ${sentiment.weekly_average ?? "?"} — news flow is well above normal.`,
    });
  }
  if (sentiment?.bullish_pct != null && sentiment.sector_avg_bullish != null) {
    const gap = sentiment.bullish_pct - sentiment.sector_avg_bullish;
    if (Math.abs(gap) > 0.2) {
      out.push({
        kind: "edge",
        title: gap > 0 ? "Outpacing sector sentiment" : "Lagging sector sentiment",
        detail: `Bullish headlines ${(sentiment.bullish_pct * 100).toFixed(0)}% vs sector ${(sentiment.sector_avg_bullish * 100).toFixed(0)}% — ${gap > 0 ? "stronger" : "weaker"} narrative than peers.`,
      });
    }
  }

  // Data confidence
  if (ai.confidence_in_data != null && ai.confidence_in_data <= 2) {
    out.push({
      kind: "conflict",
      title: "Thin data",
      detail: `Model flagged data confidence ${ai.confidence_in_data}/5 — weigh conclusions accordingly and verify with filings.`,
    });
  }

  return out;
}

/**
 * Committee spread, preferring the server's own figures.
 *
 * The backend already computes exactly these numbers in `summarize_dissent`, and
 * acts on them — they are what decides whether a rebuttal round runs. Computing
 * them a second time here means two definitions of the same statistic that can
 * drift apart, and the copy underneath would then be describing a split the
 * server did not agree was one. The local path is kept only as a fallback for
 * responses without a `dissent` block.
 */
function committeeSpread(
  committee: CommitteeEntry[] | null | undefined,
  dissent?: Dissent | null,
) {
  if (
    dissent &&
    typeof dissent.conviction_min === "number" &&
    typeof dissent.conviction_max === "number"
  ) {
    return {
      min: dissent.conviction_min,
      max: dissent.conviction_max,
      spread: dissent.conviction_spread ?? dissent.conviction_max - dissent.conviction_min,
      mean: dissent.conviction_mean ?? (dissent.conviction_min + dissent.conviction_max) / 2,
      stances: Object.keys(dissent.stances ?? {}),
      divergence: Object.keys(dissent.stances ?? {}).length,
      material: dissent.material_disagreement ?? false,
    };
  }

  if (!committee?.length) return null;
  const scores = committee
    .map((c) => c.analysis?.conviction_score)
    .filter((s): s is number => typeof s === "number");
  if (scores.length < 2) return null;
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const mean = scores.reduce((a, b) => a + b, 0) / scores.length;
  const stances = committee.map((c) => c.analysis?.stance ?? "—");
  const unique = new Set(stances.filter((s) => s !== "—"));
  return { min, max, spread: max - min, mean, stances, divergence: unique.size, material: false };
}

function SignalIntelligence({
  ai,
  committee,
  refinement,
  dissent,
  analyst,
  sentiment,
  newsSentimentMean,
}: {
  ai: AiAnalysisBlock;
  committee: CommitteeEntry[] | null;
  refinement: CommitteeRefinement | null;
  dissent: Dissent | null;
  analyst: AnalystRating | null;
  sentiment: NewsSentiment | null;
  newsSentimentMean: number | null | undefined;
}) {
  const callouts = buildCallouts({ ai, analyst, sentiment, newsSentimentMean });
  const spread = committeeSpread(committee, dissent);

  return (
    <div className="rounded-xl border border-blue-500/25 bg-surface-card p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-blue-400">
          Signal intelligence
        </h3>
        <span className="text-label text-gray-600">where data disagrees, where edge lives</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Non-consensus callouts */}
        <div className="md:col-span-2 flex flex-col gap-2">
          {callouts.length === 0 ? (
            <div className="text-xs text-gray-500 italic p-3 rounded border border-dashed border-border/60">
              No non-consensus signals yet — fetch analyst / sentiment tabs or rerun AI to populate.
            </div>
          ) : (
            callouts.map((c, i) => (
              <div
                key={i}
                className={`rounded-lg border p-3 text-xs ${
                  c.kind === "edge"
                    ? "border-amber-500/30 bg-amber-500/5"
                    : c.kind === "conflict"
                      ? "border-red-500/30 bg-red-500/5"
                      : "border-emerald-500/25 bg-emerald-500/5"
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`text-label uppercase tracking-wider font-semibold ${
                      c.kind === "edge"
                        ? "text-amber-300"
                        : c.kind === "conflict"
                          ? "text-red-300"
                          : "text-emerald-300"
                    }`}
                  >
                    {c.kind === "edge" ? "Edge" : c.kind === "conflict" ? "Caution" : "Aligned"}
                  </span>
                  <span className="text-white font-medium">{c.title}</span>
                </div>
                <p className="text-gray-400 leading-relaxed">{c.detail}</p>
              </div>
            ))
          )}
        </div>

        {/* Committee spread */}
        <div className="rounded-lg border border-border/60 bg-black/30 p-3 text-xs flex flex-col gap-2">
          <p className="text-label uppercase tracking-wider text-gray-500">Committee spread</p>
          {spread ? (
            <>
              <div className="flex items-baseline justify-between">
                <span className="text-gray-400">Conviction range</span>
                <span className="font-mono text-white">
                  {spread.min.toFixed(0)}–{spread.max.toFixed(0)}
                </span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-gray-400">Mean</span>
                <span className="font-mono text-white">{spread.mean.toFixed(0)}</span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-gray-400">Stance divergence</span>
                <span
                  className={`font-mono ${
                    spread.divergence >= 3
                      ? "text-red-300"
                      : spread.divergence === 2
                        ? "text-amber-300"
                        : "text-emerald-300"
                  }`}
                >
                  {spread.divergence === 1 ? "Unanimous" : `${spread.divergence} stances`}
                </span>
              </div>
              <div className="mt-1 pt-2 border-t border-border/40 text-label text-gray-500 leading-relaxed">
                {/* The spread above is the post-rebuttal one. Calling a talked-down
                    split "robust to style" would be a straightforward lie, so
                    agreement reached after a second round is labelled as such. */}
                {refinement?.triggered
                  ? spread.material
                    ? "Still split after a rebuttal round — the disagreement survived being argued out. Read both theses before sizing."
                    : "Agreement reached only after a rebuttal round, not first time. Weaker evidence than an unprompted consensus."
                  : spread.material
                    ? "Materially split, and no rebuttal round ran — the synthesis reconciled this without the analysts ever answering each other."
                    : spread.divergence >= 3
                      ? "Strong disagreement — high information content in the thesis; verify assumptions."
                      : spread.divergence === 2
                        ? "Split committee — look for the dissenting view's thesis before sizing."
                        : "Consensus across lenses — thesis is robust to style."}
              </div>

              {refinement?.triggered && (
                <div className="mt-2 pt-2 border-t border-border/40 space-y-1">
                  <div className="flex items-baseline justify-between">
                    <span className="text-gray-400">Rebuttal round</span>
                    <span className="font-mono tabular text-white">
                      {refinement.conviction_spread_before ?? "—"} →{" "}
                      {refinement.conviction_spread_after ?? "—"}
                    </span>
                  </div>
                  {(refinement.held_personas?.length ?? 0) > 0 && (
                    <div className="flex items-baseline justify-between">
                      <span className="text-gray-400">Held</span>
                      <span className="font-mono tabular text-emerald-300">
                        {refinement.held_personas!.length}
                      </span>
                    </div>
                  )}
                  {(refinement.revised_personas?.length ?? 0) > 0 && (
                    <div className="flex items-baseline justify-between">
                      <span className="text-gray-400">Revised</span>
                      <span className="font-mono tabular text-amber-300">
                        {refinement.revised_personas!.length}
                      </span>
                    </div>
                  )}
                  {refinement.suspect_convergence && (
                    <p className="text-label text-red-300 leading-relaxed">
                      Every dissenting analyst moved to the same view in one round — treat as
                      deference to the group, not independent agreement.
                    </p>
                  )}
                </div>
              )}
            </>
          ) : (
            <p className="text-gray-500 italic">Run committee mode to see spread.</p>
          )}
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Alt Data sub-components
// ------------------------------------------------------------------

function InsiderFlowCard({ data, loading }: { data: InsiderTransaction[]; loading: boolean }) {
  const net = useMemo(() => {
    let buy = 0;
    let sell = 0;
    let buyCount = 0;
    let sellCount = 0;
    for (const t of data.slice(0, 50)) {
      const isSell = (t.transaction_type ?? "").toLowerCase().includes("sale");
      const val = Number(t.value ?? 0);
      if (isSell) {
        sell += val;
        sellCount += 1;
      } else {
        buy += val;
        buyCount += 1;
      }
    }
    return { buy, sell, buyCount, sellCount, net: buy - sell };
  }, [data]);

  const total = net.buy + net.sell;
  const buyPct = total > 0 ? (net.buy / total) * 100 : 0;

  return (
    <div className="bg-surface-card rounded-xl p-4">
      <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">Insider flow (last 50)</h3>
      {loading && <p className="text-sm text-gray-500">Loading…</p>}
      {!loading && data.length === 0 && <p className="text-sm text-gray-500">No recent insider activity.</p>}
      {!loading && data.length > 0 && (
        <>
          <div className="flex items-baseline gap-2">
            <p
              className={`text-2xl font-mono font-bold ${
                net.net >= 0 ? "text-accent-green" : "text-accent-red"
              }`}
            >
              {net.net >= 0 ? "+" : ""}${(net.net / 1e6).toFixed(1)}M
            </p>
            <span className="text-xs text-gray-500">net</span>
          </div>
          <div className="flex items-center gap-1 mt-2 h-1.5 rounded overflow-hidden bg-red-500/40">
            <div
              className="h-full bg-emerald-500/80"
              style={{ width: `${Math.max(0, Math.min(100, buyPct))}%` }}
            />
          </div>
          <div className="grid grid-cols-2 gap-2 mt-3 text-xs">
            <div>
              <p className="text-emerald-400">Buys · {net.buyCount}</p>
              <p className="text-gray-500 font-mono">${(net.buy / 1e6).toFixed(1)}M</p>
            </div>
            <div className="text-right">
              <p className="text-red-400">Sells · {net.sellCount}</p>
              <p className="text-gray-500 font-mono">${(net.sell / 1e6).toFixed(1)}M</p>
            </div>
          </div>
          <div className="mt-3 pt-3 border-t border-border/50">
            <p className="text-label text-gray-600 uppercase tracking-wider mb-1">Recent</p>
            {data.slice(0, 4).map((t, i) => (
              <div key={i} className="flex justify-between py-0.5 text-label">
                <span className="text-gray-400 truncate mr-2">{t.name}</span>
                <span
                  className={`font-mono ${
                    (t.transaction_type ?? "").toLowerCase().includes("sale")
                      ? "text-red-400"
                      : "text-emerald-400"
                  }`}
                >
                  {(t.transaction_type ?? "").toLowerCase().includes("sale") ? "−" : "+"}$
                  {((t.value ?? 0) / 1e3).toFixed(0)}k
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function CongressionalCard({
  data,
  loading,
}: {
  data: CongressionalTrade[];
  loading: boolean;
}) {
  return (
    <div className="bg-surface-card rounded-xl p-4">
      <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">
        Congressional trades
      </h3>
      {loading && <p className="text-sm text-gray-500">Loading…</p>}
      {!loading && data.length === 0 && (
        <p className="text-sm text-gray-500">
          None disclosed (or Finnhub not configured).
        </p>
      )}
      {!loading && data.length > 0 && (
        <div className="flex flex-col gap-1.5">
          {data.slice(0, 8).map((t, i) => (
            <div key={i} className="flex justify-between items-start text-xs">
              <div className="min-w-0 flex-1">
                <p className="text-gray-300 truncate">{t.representative}</p>
                <p className="text-label text-gray-600">
                  {t.chamber ?? ""}{t.chamber ? " · " : ""}
                  {t.transaction_date ?? t.disclosure_date ?? ""}
                </p>
              </div>
              <div className="text-right shrink-0 ml-2">
                <p
                  className={`font-mono ${
                    (t.transaction_type ?? "").toLowerCase().includes("sale")
                      ? "text-red-400"
                      : "text-emerald-400"
                  }`}
                >
                  {t.transaction_type}
                </p>
                <p className="text-label text-gray-500 truncate max-w-[8rem]">{t.amount_range ?? "—"}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ESGCard({ data, loading }: { data: ESGScores | null; loading: boolean }) {
  return (
    <div className="bg-surface-card rounded-xl p-4">
      <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">ESG score</h3>
      {loading && <p className="text-sm text-gray-500">Loading…</p>}
      {!loading && !data && <p className="text-sm text-gray-500">ESG unavailable (set FINNHUB_API_KEY).</p>}
      {!loading && data && (
        <>
          <div className="flex items-baseline gap-2">
            <p className="text-3xl font-mono font-bold text-white">
              {data.total_score != null ? data.total_score.toFixed(0) : "—"}
            </p>
            <span className="text-xs text-gray-500">/ 100</span>
          </div>
          <div className="grid grid-cols-3 gap-2 mt-3 text-xs">
            <div>
              <p className="text-label text-gray-600 uppercase">Env</p>
              <p className="text-gray-200 font-mono">
                {data.environment_score != null ? data.environment_score.toFixed(0) : "—"}
              </p>
            </div>
            <div>
              <p className="text-label text-gray-600 uppercase">Social</p>
              <p className="text-gray-200 font-mono">
                {data.social_score != null ? data.social_score.toFixed(0) : "—"}
              </p>
            </div>
            <div>
              <p className="text-label text-gray-600 uppercase">Gov</p>
              <p className="text-gray-200 font-mono">
                {data.governance_score != null ? data.governance_score.toFixed(0) : "—"}
              </p>
            </div>
          </div>
          {data.controversy_level != null && (
            <p className="text-label text-gray-500 mt-3">
              Controversy level: <span className="text-amber-300 font-mono">{data.controversy_level}</span>
              {data.peer_group ? ` · peer group ${data.peer_group}` : ""}
            </p>
          )}
        </>
      )}
    </div>
  );
}

function FilingsCard({ data, loading }: { data: SECFiling[]; loading: boolean }) {
  if (loading) {
    return (
      <div className="bg-surface-card rounded-xl p-4">
        <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">Recent SEC filings</h3>
        <p className="text-sm text-gray-500">Loading…</p>
      </div>
    );
  }
  if (!data?.length) {
    return (
      <div className="bg-surface-card rounded-xl p-4">
        <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">Recent SEC filings</h3>
        <p className="text-sm text-gray-500">No filings available (requires Finnhub or EDGAR access).</p>
      </div>
    );
  }

  return (
    <div className="bg-surface-card rounded-xl p-4">
      <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">
        Recent SEC filings ({data.length})
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-border">
              <th className="text-left py-1">Form</th>
              <th className="text-left py-1">Filed</th>
              <th className="text-left py-1">Description</th>
              <th className="text-right py-1">Link</th>
            </tr>
          </thead>
          <tbody>
            {data.slice(0, 15).map((f, i) => (
              <tr key={i} className="border-b border-border/50">
                <td className="py-1">
                  <span
                    className={`px-1.5 py-0.5 rounded font-mono text-label ${
                      f.form_type?.startsWith("4")
                        ? "bg-emerald-500/20 text-emerald-300"
                        : f.form_type === "13F" || f.form_type?.startsWith("13")
                          ? "bg-purple-500/20 text-purple-300"
                          : f.form_type === "8-K"
                            ? "bg-amber-500/20 text-amber-300"
                            : "bg-surface-elevated text-gray-300"
                    }`}
                  >
                    {f.form_type}
                  </span>
                </td>
                <td className="text-gray-400 py-1">{f.filed_date ?? "—"}</td>
                <td className="text-gray-300 py-1 truncate max-w-xs">{f.description ?? "—"}</td>
                <td className="text-right py-1">
                  {f.report_url ? (
                    <a
                      href={f.report_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="text-blue-400 hover:underline"
                    >
                      View
                    </a>
                  ) : (
                    <span className="text-gray-600">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-label text-gray-600 mt-2">
        Form 4 = insider · 13F = institutional · 8-K = material events · 10-K/Q = financials.
      </p>
    </div>
  );
}

// ------------------------------------------------------------------
// Peers tab
// ------------------------------------------------------------------

const PEER_METRIC_KEYS: { key: string; label: string; fmt?: (v: number) => string }[] = [
  { key: "pe_ratio", label: "P/E" },
  { key: "forward_pe", label: "Fwd P/E" },
  { key: "price_to_book", label: "P/B" },
  { key: "profit_margin", label: "Margin", fmt: (v) => `${(v * 100).toFixed(1)}%` },
  { key: "return_on_equity", label: "ROE", fmt: (v) => `${(v * 100).toFixed(1)}%` },
  { key: "revenue_growth", label: "Rev g", fmt: (v) => `${(v * 100).toFixed(1)}%` },
  { key: "dividend_yield", label: "Div", fmt: (v) => `${(v * 100).toFixed(2)}%` },
  { key: "beta", label: "Beta" },
];

function PeersTab({ data, currentTicker }: { data: PeerComparison; currentTicker: string }) {
  const rows = useMemo(() => {
    const all = [currentTicker, ...(data.peers ?? [])];
    return all.map((t) => ({
      ticker: t,
      metrics: (data.metrics?.[t] ?? {}) as Record<string, number | null>,
    }));
  }, [data, currentTicker]);

  // Radar: normalise each metric 0..1 across peers (higher is NOT always better, just relative)
  const radarData = useMemo(() => {
    const keys = ["pe_ratio", "profit_margin", "return_on_equity", "revenue_growth", "beta"];
    return keys.map((k) => {
      const vals = rows.map((r) => r.metrics[k]).filter((v): v is number => typeof v === "number");
      const max = Math.max(...vals, 0.0001);
      const entry: Record<string, number | string> = {
        factor: PEER_METRIC_KEYS.find((m) => m.key === k)?.label ?? k,
      };
      for (const r of rows) {
        const v = typeof r.metrics[k] === "number" ? r.metrics[k]! : 0;
        entry[r.ticker] = max > 0 ? v / max : 0;
      }
      return entry;
    });
  }, [rows]);

  if (!data.peers?.length) {
    return (
      <EmptyState
        message={`No peers found in ${data.industry ?? data.sector ?? "this sector"}. Try another symbol.`}
      />
    );
  }

  // Palette from DESIGN.md — primary blue + semantic + info + muted neutral
  const accentColors = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#38bdf8", "#a1a1aa"];

  return (
    <div className="flex flex-col gap-4">
      <div className="bg-surface-card rounded-xl p-4">
        <div className="flex items-start justify-between mb-3">
          <div>
            <h3 className="text-xs text-gray-500 uppercase tracking-wider">Peer group</h3>
            <p className="text-sm text-gray-300 mt-1">
              {data.industry ?? "—"} · {data.sector ?? "—"}
            </p>
          </div>
          <p className="text-xs text-gray-500">{data.peers.length} peers</p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 border-b border-border">
                <th className="text-left py-2 pr-3">Ticker</th>
                {PEER_METRIC_KEYS.map((m) => (
                  <th key={m.key} className="text-right py-2 px-2">
                    {m.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const isSelf = r.ticker === currentTicker;
                return (
                  <tr
                    key={r.ticker}
                    className={`border-b border-border/50 ${isSelf ? "bg-blue-500/5" : ""}`}
                  >
                    <td className="py-2 pr-3">
                      <span
                        className={`font-mono font-semibold ${
                          isSelf ? "text-blue-300" : "text-gray-200"
                        }`}
                      >
                        {r.ticker}
                      </span>
                      {isSelf && <span className="text-label text-blue-400/80 ml-2">(this)</span>}
                    </td>
                    {PEER_METRIC_KEYS.map((m) => {
                      const v = r.metrics[m.key];
                      return (
                        <td key={m.key} className="text-right py-2 px-2 font-mono text-gray-300">
                          {typeof v === "number"
                            ? m.fmt
                              ? m.fmt(v)
                              : v.toFixed(2)
                            : "—"}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Radar — normalized metrics */}
      {rows.length > 1 && radarData.length > 0 && (
        <div className="bg-surface-card rounded-xl p-4">
          <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">
            Relative profile (normalized 0–1 across peer group)
          </h3>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData}>
                <PolarGrid stroke="#3f3f46" />
                <PolarAngleAxis dataKey="factor" tick={{ fill: "#a1a1aa", fontSize: 11 }} />
                <PolarRadiusAxis tick={{ fill: "#52525b", fontSize: 9 }} />
                {rows.slice(0, 6).map((r, i) => (
                  <Radar
                    key={r.ticker}
                    name={r.ticker}
                    dataKey={r.ticker}
                    stroke={accentColors[i % accentColors.length]}
                    fill={accentColors[i % accentColors.length]}
                    fillOpacity={r.ticker === currentTicker ? 0.35 : 0.12}
                    strokeWidth={r.ticker === currentTicker ? 2 : 1}
                  />
                ))}
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: "#0b0b0b", border: "1px solid #27272a", fontSize: 12 }}
                />
              </RadarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-label text-gray-600 mt-2">
            Each axis is normalized against the peer maximum — larger polygon = stronger relative profile. Compare
            shape differences to spot where this name leads or lags peers.
          </p>
        </div>
      )}

      {/* Per-metric bar races */}
      <div className="bg-surface-card rounded-xl p-4">
        <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">Side-by-side</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {(["pe_ratio", "profit_margin", "return_on_equity", "revenue_growth"] as const).map((key) => {
            const label = PEER_METRIC_KEYS.find((m) => m.key === key)?.label ?? key;
            const chartRows = rows
              .map((r) => ({
                ticker: r.ticker,
                value: typeof r.metrics[key] === "number" ? r.metrics[key]! : 0,
                isSelf: r.ticker === currentTicker,
              }))
              .filter((r) => r.value !== 0);
            if (!chartRows.length) return null;
            return (
              <div key={key} className="h-40">
                <p className="text-label text-gray-500 uppercase tracking-wider mb-1">{label}</p>
                <ResponsiveContainer width="100%" height="85%">
                  <BarChart data={chartRows} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis type="number" tick={{ fill: "#71717a", fontSize: 10 }} />
                    <YAxis
                      type="category"
                      dataKey="ticker"
                      tick={{ fill: "#a1a1aa", fontSize: 10 }}
                      width={60}
                    />
                    <Tooltip
                      contentStyle={{ background: "#0b0b0b", border: "1px solid #27272a", fontSize: 12 }}
                    />
                    <Bar
                      dataKey="value"
                      fill="#60a5fa"
                      shape={(props: unknown) => {
                        const { x, y, width, height, payload } = props as {
                          x: number;
                          y: number;
                          width: number;
                          height: number;
                          payload: { isSelf: boolean };
                        };
                        return (
                          <rect
                            x={x}
                            y={y}
                            width={width}
                            height={height}
                            fill={payload?.isSelf ? "#f59e0b" : "#3b82f6"}
                            opacity={payload?.isSelf ? 1 : 0.7}
                          />
                        );
                      }}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="bg-surface-card rounded-xl p-8 text-center">
      <p className="text-gray-500 text-sm">{message}</p>
    </div>
  );
}

// ------------------------------------------------------------------
// Backtest tab
// ------------------------------------------------------------------

function BacktestTab({ ticker }: { ticker: string }) {
  const [strategy, setStrategy] = useState("golden_cross");
  const [days, setDays] = useState(1095); // 3y

  const strategies = useQuery({
    queryKey: ["backtest-strategies"],
    queryFn: () => api.listStrategies(),
    staleTime: 60_000 * 60,
  });

  const backtest = useQuery({
    queryKey: ["backtest", ticker, strategy, days],
    queryFn: () => api.runBacktest(ticker, strategy, { days }),
    enabled: !!ticker,
    retry: false,
  });

  const strategyList = strategies.data?.strategies ?? [];
  const d = backtest.data;

  // Downsample the equity curve for chart perf (keep at most 500 points)
  const chartData = useMemo(() => {
    if (!d?.equity_curve?.length) return [];
    const src = d.equity_curve;
    const step = Math.max(1, Math.floor(src.length / 500));
    return src
      .filter((_, i) => i % step === 0 || i === src.length - 1)
      .map((p) => ({
        date: p.date,
        strategy: +((p.equity - 1) * 100).toFixed(2),
        buyhold: +((p.benchmark - 1) * 100).toFixed(2),
        position: p.position,
      }));
  }, [d]);

  return (
    <div className="flex flex-col gap-4">
      {/* Controls */}
      <div className="bg-surface-card rounded-xl p-4">
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex flex-col gap-1">
            <label className="text-label uppercase tracking-wider text-gray-500">
              Strategy
            </label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="bg-surface-elevated border border-border rounded px-3 py-1.5 text-sm text-white min-w-[240px]"
            >
              {strategyList.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-label uppercase tracking-wider text-gray-500">
              Window
            </label>
            <select
              value={days}
              onChange={(e) => setDays(+e.target.value)}
              className="bg-surface-elevated border border-border rounded px-3 py-1.5 text-sm text-white"
            >
              <option value={365}>1y</option>
              <option value={730}>2y</option>
              <option value={1095}>3y</option>
              <option value={1825}>5y</option>
              <option value={3650}>10y</option>
            </select>
          </div>
          <p className="text-label text-gray-500 ml-auto max-w-sm">
            No look-ahead · 5 bps fee per side · signals computed on close, executed next bar.
          </p>
        </div>
        {strategyList.find((s) => s.id === strategy)?.description && (
          <p className="text-xs text-gray-400 mt-3">
            {strategyList.find((s) => s.id === strategy)?.description}
          </p>
        )}
      </div>

      {backtest.isLoading && <EmptyState message="Running backtest…" />}
      {backtest.isError && (
        <div className="bg-amber-900/20 border border-amber-700/40 rounded-xl p-4 text-sm text-amber-200">
          Backtest failed: {(backtest.error as Error).message}
        </div>
      )}
      {d && (
        <>
          {/* Metric cards — strategy vs benchmark */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard
              label="Total return"
              strategy={d.metrics.total_return}
              benchmark={d.benchmark_metrics.total_return}
              fmt="pct"
            />
            <MetricCard
              label="CAGR"
              strategy={d.metrics.cagr}
              benchmark={d.benchmark_metrics.cagr}
              fmt="pct"
            />
            <MetricCard
              label="Sharpe"
              strategy={d.metrics.sharpe}
              benchmark={d.benchmark_metrics.sharpe}
              fmt="num"
              higherIsBetter
            />
            <MetricCard
              label="Max drawdown"
              strategy={d.metrics.max_drawdown}
              benchmark={d.benchmark_metrics.max_drawdown}
              fmt="pct"
              higherIsBetter
              dd
            />
          </div>

          {/* Equity curve */}
          <div className="bg-surface-card rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs text-gray-500 uppercase tracking-wider">
                Cumulative return — strategy vs buy &amp; hold
              </h3>
              <span className="text-label text-gray-600 font-mono">
                {d.start_date} → {d.end_date}
              </span>
            </div>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: "#71717a", fontSize: 10 }}
                    minTickGap={60}
                  />
                  <YAxis
                    tick={{ fill: "#71717a", fontSize: 10 }}
                    width={48}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "#121214",
                      border: "1px solid #27272a",
                      fontSize: 12,
                    }}
                    labelStyle={{ color: "#a1a1aa" }}
                    formatter={(v: number, name: string) => [
                      `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`,
                      name === "strategy" ? "Strategy" : "Buy & hold",
                    ]}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: 11 }}
                    iconType="plainline"
                    formatter={(v) => (v === "strategy" ? "Strategy" : "Buy & hold")}
                  />
                  <Line
                    type="monotone"
                    dataKey="buyhold"
                    stroke="#a1a1aa"
                    strokeWidth={1.2}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="strategy"
                    stroke="#3b82f6"
                    strokeWidth={1.8}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Secondary metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <SmallStat label="Sortino" value={d.metrics.sortino.toFixed(2)} />
            <SmallStat label="Calmar" value={d.metrics.calmar.toFixed(2)} />
            <SmallStat
              label="Volatility (ann)"
              value={`${(d.metrics.volatility * 100).toFixed(1)}%`}
            />
            <SmallStat
              label="Win rate (bars)"
              value={`${(d.metrics.win_rate * 100).toFixed(0)}%`}
            />
            <SmallStat
              label="Time in market"
              value={`${(d.metrics.time_in_market * 100).toFixed(0)}%`}
            />
            <SmallStat label="Round-trips" value={String(d.metrics.num_trades)} />
            <SmallStat label="Bars" value={String(d.metrics.n_bars)} />
            <SmallStat label="Years" value={d.metrics.years.toFixed(2)} />
          </div>

          {/* Trade log */}
          {d.trades.length > 0 && (
            <div className="bg-surface-card rounded-xl p-4">
              <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">
                Trade log ({d.trades.length} round-trips)
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-500 border-b border-border">
                      <th className="text-left py-1">Entry</th>
                      <th className="text-right py-1">Price</th>
                      <th className="text-left py-1">Exit</th>
                      <th className="text-right py-1">Price</th>
                      <th className="text-right py-1">Days</th>
                      <th className="text-right py-1">P&amp;L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.trades.map((t, i) => (
                      <tr key={i} className="border-b border-border/50">
                        <td className="text-gray-400 py-1">{t.entry_date}</td>
                        <td className="text-right text-gray-200 font-mono">
                          ${t.entry_price.toFixed(2)}
                        </td>
                        <td className="text-gray-400 py-1">{t.exit_date}</td>
                        <td className="text-right text-gray-200 font-mono">
                          ${t.exit_price.toFixed(2)}
                        </td>
                        <td className="text-right text-gray-500 font-mono">{t.days_held}</td>
                        <td
                          className={`text-right font-mono font-semibold ${
                            t.return_pct >= 0 ? "text-accent-green" : "text-accent-red"
                          }`}
                        >
                          {t.return_pct >= 0 ? "+" : ""}
                          {t.return_pct.toFixed(2)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function MetricCard({
  label,
  strategy,
  benchmark,
  fmt,
  higherIsBetter = true,
  dd = false,
}: {
  label: string;
  strategy: number;
  benchmark: number;
  fmt: "pct" | "num";
  higherIsBetter?: boolean;
  dd?: boolean;
}) {
  const fmtVal = (v: number) => {
    if (fmt === "pct") {
      const pct = v * 100;
      return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
    }
    return v.toFixed(2);
  };

  // For drawdown, "higher" (less negative) is better
  const effectiveStrategy = dd ? strategy : strategy;
  const effectiveBenchmark = dd ? benchmark : benchmark;
  const beats = higherIsBetter
    ? effectiveStrategy > effectiveBenchmark
    : effectiveStrategy < effectiveBenchmark;

  const valueClass =
    fmt === "pct"
      ? strategy >= 0
        ? "text-accent-green"
        : "text-accent-red"
      : "text-white";

  return (
    <div className="bg-surface-card rounded-xl p-3 border border-border/60">
      <p className="text-label text-gray-500 uppercase tracking-wider">{label}</p>
      <p className={`text-xl font-bold font-mono mt-1 ${valueClass}`}>{fmtVal(strategy)}</p>
      <div className="flex items-center justify-between text-label mt-1">
        <span className="text-gray-600">vs buy-hold</span>
        <span className="font-mono text-gray-500">{fmtVal(benchmark)}</span>
      </div>
      <div
        className={`mt-2 text-label font-semibold uppercase tracking-wider ${
          beats ? "text-accent-green" : "text-accent-red"
        }`}
      >
        {beats ? "↑ Beats" : "↓ Lags"}
      </div>
    </div>
  );
}

function SmallStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-surface-card rounded-lg p-2.5 border border-border/40">
      <p className="text-label text-gray-500 uppercase tracking-wider">{label}</p>
      <p className="text-sm text-white font-mono mt-0.5">{value}</p>
    </div>
  );
}

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

function fmtLarge(val: number | null | undefined): string {
  if (val == null) return "N/A";
  const abs = Math.abs(val);
  const sign = val < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(1)}T`;
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(0)}M`;
  return `${sign}$${abs.toLocaleString()}`;
}
