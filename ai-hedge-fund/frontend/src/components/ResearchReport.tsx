import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  api,
  type EarningsInfo,
  type AnalystRating,
  type InsiderTransaction,
  type InstitutionalHolder,
  type NewsSentiment,
  type OptionsChain,
  type ResearchCheckResponse,
} from "@/lib/api";
import { ChatInput } from "./ChatInput";
import { ConvictionGauge } from "./ConvictionGauge";
import { PriceChart } from "./PriceChart";
import { AppNav } from "./AppNav";
import { PersonaOpinionGrid, PersonaCard, humanizePersonaId, SynthesisCard } from "./PersonaOpinionCards";

const TABS = ["Investor views", "Fundamental", "Technical", "Sentiment", "Macro", "Institutional"] as const;

export function ResearchReport() {
  const { ticker: paramTicker } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<string>("Investor views");
  const [includeAi, setIncludeAi] = useState(false);
  /** default = generic analyst; committee = multi persona + PM synthesis; persona = one named style */
  const [investorMode, setInvestorMode] = useState<"default" | "committee" | "persona">("committee");
  const [personaId, setPersonaId] = useState("warren_buffett");
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

  const handleSearch = (query: string) => {
    const t = query.replace(/^check\s+/i, "").trim().toUpperCase();
    if (t) navigate(`/research/${t}`);
  };

  if (!ticker) {
    return (
      <div className="flex flex-col h-screen">
        <AppNav active="research" />
        <div className="grow flex items-center justify-center">
          <div className="w-full max-w-lg">
            <h1 className="text-2xl font-bold text-white mb-4 text-center">Research a Ticker</h1>
            <ChatInput onSubmit={handleSearch} placeholder="Enter a ticker symbol (e.g. AAPL, THYAO.IS)" />
          </div>
        </div>
      </div>
    );
  }

  const d = research.data as ResearchCheckResponse | undefined;
  const fundamentals = (d?.fundamentals ?? {}) as Record<string, unknown>;
  const technicals = (d?.technicals ?? {}) as Record<string, unknown>;
  const ai = d?.ai_full;

  return (
    <div className="flex flex-col h-screen">
      <AppNav
        active="research"
        end={
          <div className="w-80">
            <ChatInput onSubmit={handleSearch} placeholder="Check another ticker..." />
          </div>
        }
      />

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

          <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={includeAi}
              onChange={(e) => setIncludeAi(e.target.checked)}
              className="rounded border-border"
            />
            Run AI thesis &amp; conviction (local Ollama by default — see README)
          </label>

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
                    className={`text-[11px] px-2 py-1 rounded-md border bg-black/20 ${col}`}
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
            <PriceChart data={priceData.data?.data ?? []} />
          </div>

          {/* ================================================================ */}
          {/* INVESTOR VIEWS TAB */}
          {/* ================================================================ */}
          {activeTab === "Investor views" && (
            <div className="flex flex-col gap-4">
              {!includeAi && (
                <div className="bg-surface-card rounded-xl p-8 text-center border border-dashed border-border">
                  <p className="text-gray-400 text-sm">
                    Turn on <strong className="text-gray-300">Run AI thesis</strong> above, then choose{" "}
                    <strong className="text-gray-300">Committee</strong> or <strong className="text-gray-300">Single investor</strong>{" "}
                    to see named investor takes on this symbol.
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
                  ["P/E Ratio", fundamentals.pe_ratio],
                  ["Forward P/E", fundamentals.forward_pe],
                  ["PEG Ratio", fundamentals.peg_ratio],
                  ["P/B Ratio", fundamentals.price_to_book],
                  ["Div Yield", fundamentals.dividend_yield ? `${(fundamentals.dividend_yield as number * 100).toFixed(2)}%` : "N/A"],
                  ["Beta", fundamentals.beta],
                  ["Market Cap", fundamentals.market_cap ? `$${((fundamentals.market_cap as number) / 1e9).toFixed(1)}B` : "N/A"],
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
                  ["Current", d?.price?.current ? `$${d.price.current}` : "N/A"],
                  ["52w High", fundamentals["52w_high"] ? `$${fundamentals["52w_high"]}` : "N/A"],
                  ["52w Low", fundamentals["52w_low"] ? `$${fundamentals["52w_low"]}` : "N/A"],
                  ["30d Change", d?.price?.change_30d_pct ? `${d.price.change_30d_pct}%` : "N/A"],
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
        </main>

        {/* Right sidebar */}
        <aside className="w-72 border-l border-border p-4 overflow-y-auto flex flex-col gap-4">
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
                  <p className="text-[10px] text-gray-600 mt-2 truncate" title={d.news_sentiment.model ?? ""}>
                    {d.news_sentiment.model ?? "model"}
                  </p>
                </>
              ) : (
                <p className="text-xs text-gray-500">
                  {d.news_sentiment.reason === "transformers_not_installed"
                    ? "Install API extras: uv sync --extra sentiment"
                    : d.news_sentiment.reason ?? "Off"}
                </p>
              )}
            </div>
          )}
        </aside>
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

function MacroTab() {
  const famaFrench = useQuery({
    queryKey: ["fama-french"],
    queryFn: () => api.getFamaFrench(),
    retry: false,
  });

  return (
    <>
      {famaFrench.data && (
        <div className="bg-surface-card rounded-xl p-4">
          <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">
            Fama-French 5-Factor ({famaFrench.data.period})
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

      <div className="bg-surface-card rounded-xl p-4">
        <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">FRED Macro Series</h3>
        <p className="text-sm text-gray-400">
          Use the Macro endpoint to query FRED series: GDP, UNRATE, CPIAUCSL, DFF, T10Y2Y, etc.
        </p>
      </div>
    </>
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
