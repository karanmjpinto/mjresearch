/**
 * API client.
 *
 * In development, calls are relative and the Vite proxy forwards /api to
 * FastAPI on :8000. A static deploy (GitHub Pages) has no backend on its own
 * origin, so set VITE_API_BASE_URL at build time to the deployed API root —
 * otherwise every request 404s against the static host.
 */

const CONFIGURED = import.meta.env.VITE_API_BASE_URL?.trim();
const BASE = CONFIGURED ? `${CONFIGURED.replace(/\/+$/, "")}/api` : "/api";

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

async function postJSON<T>(path: string, data: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

export interface YartsevaResultRow {
  ticker: string;
  stage1_passed: boolean;
  stage1_failures: string[];
  composite: number | null;
  tier: string | null;
  short_sell_flag: boolean;
  error?: string | null;
  fcf_yield_score?: number | null;
  value_score?: number | null;
  profitability_score?: number | null;
  investment_quality_score?: number | null;
  size_score?: number | null;
  entry_timing_score?: number | null;
  fcf_yield_pct?: number | null;
  book_to_market?: number | null;
  roa_pct?: number | null;
  asset_growth_pct?: number | null;
  ebitda_growth_pct?: number | null;
  inv_excess_pp?: number | null;
  entry_range_pct?: number | null;
  snapshot?: Record<string, unknown>;
}

export interface YartsevaScreenerResponse {
  macro_regime_note: string;
  watchlist_group: string | null;
  universe?: string | null;
  universe_total?: number | null;
  universe_truncated?: boolean;
  max_symbols?: number | null;
  tickers: string[];
  count: number;
  results: YartsevaResultRow[];
}

export interface AcquisitionCompounderResultRow {
  ticker: string;
  stage1_passed: boolean;
  stage1_failures: string[];
  tier2_passed: boolean;
  red_flags: string[];
  industry_avoid: boolean;
  industry_prefer_match: boolean;
  total_score: number | null;
  tier: string | null;
  scores: Record<string, number>;
  error?: string | null;
  snapshot?: Record<string, unknown>;
}

export interface AcquisitionCompounderScreenerResponse {
  methodology_note: string;
  watchlist_group: string | null;
  universe?: string | null;
  universe_total?: number | null;
  universe_truncated?: boolean;
  max_symbols?: number | null;
  tickers: string[];
  count: number;
  results: AcquisitionCompounderResultRow[];
}

export interface ScreenerUniverseMeta {
  id: string;
  label: string;
  description: string;
  approx_count: number;
}

async function patchJSON<T>(path: string, data: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

// ------------------------------------------------------------------
// Types — new data categories
// ------------------------------------------------------------------

export interface ESGScores {
  ticker: string;
  total_score: number | null;
  environment_score: number | null;
  social_score: number | null;
  governance_score: number | null;
  controversy_level?: number | null;
  peer_group?: string | null;
  source: string;
}

export interface InsiderTransaction {
  ticker: string;
  name: string;
  title?: string | null;
  transaction_type: string;
  shares: number;
  value: number | null;
  date: string | null;
  source: string;
}

export interface InstitutionalHolder {
  ticker: string;
  holder: string;
  shares: number;
  value: number | null;
  pct_held: number | null;
  date_reported: string | null;
  source: string;
}

export interface EarningsInfo {
  ticker: string;
  next_earnings_date: string | null;
  earnings_dates: Array<{
    date: string;
    eps_estimate: number | null;
    reported_eps: number | null;
    surprise_pct: number | null;
  }>;
  quarterly_earnings: Array<{
    quarter: string;
    revenue: number | null;
    earnings: number | null;
  }>;
  source: string;
}

export interface AnalystRating {
  ticker: string;
  target_mean: number | null;
  target_median: number | null;
  target_high: number | null;
  target_low: number | null;
  current_price: number | null;
  upside_pct: number | null;
  num_analysts: number | null;
  recommendation: string | null;
  recommendation_history: Array<{
    date: string;
    firm: string;
    grade: string;
    action: string;
  }>;
  source: string;
}

export interface NewsSentiment {
  ticker: string;
  /** False when no provider key is configured. FinBERT headline sentiment is
   *  separate and unaffected — see the research snapshot. */
  available?: boolean;
  reason?: string;
  detail?: string;
  buzz_score: number | null;
  articles_in_last_week: number | null;
  weekly_average: number | null;
  company_news_score: number | null;
  sector_avg_bullish: number | null;
  sector_avg_news_score: number | null;
  bearish_pct: number | null;
  bullish_pct: number | null;
  source: string;
}

export interface SectorPerformance {
  realtime: Array<{ sector: string; change_pct: number }>;
  one_day: Array<{ sector: string; change_pct: number }>;
  five_day: Array<{ sector: string; change_pct: number }>;
  one_month: Array<{ sector: string; change_pct: number }>;
  three_month: Array<{ sector: string; change_pct: number }>;
  ytd: Array<{ sector: string; change_pct: number }>;
  one_year: Array<{ sector: string; change_pct: number }>;
  source: string;
}

export interface FamaFrenchFactors {
  period: string;
  factors: Array<{
    date: string;
    "Mkt-RF": number;
    SMB: number;
    HML: number;
    RMW: number;
    CMA: number;
    RF: number;
  }>;
  source: string;
}

export interface OptionsChain {
  ticker: string;
  expirations: string[];
  calls: Record<string, unknown>[];
  puts: Record<string, unknown>[];
  source: string;
}

export interface SECFiling {
  ticker: string;
  form_type: string;
  filed_date: string | null;
  accepted_date: string | null;
  report_url: string | null;
  description?: string | null;
  source: string;
}

export interface CongressionalTrade {
  ticker: string;
  representative: string;
  transaction_type: string;
  amount_range: string | null;
  transaction_date: string | null;
  disclosure_date?: string | null;
  chamber?: string | null;
  source: string;
}

export interface PeerComparison {
  ticker: string;
  peers: string[];
  sector: string | null;
  industry: string | null;
  metrics: Record<string, Record<string, number | null>>;
  source: string;
}

export interface ProviderStatus {
  name: string;
  available: boolean;
  categories: string[];
  priority: number;
  rate_limit: Record<string, unknown> | null;
}

// ------------------------------------------------------------------
// Backtest types
// ------------------------------------------------------------------

export interface BacktestStrategyDef {
  id: string;
  name: string;
  description: string;
  default_params: Record<string, number>;
  category: "trend" | "mean_reversion" | "volatility" | "benchmark";
}

export interface BacktestMetrics {
  total_return: number;
  cagr: number;
  volatility: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  calmar: number;
  win_rate: number;
  time_in_market: number;
  num_trades: number;
  n_bars: number;
  years: number;
}

export interface BacktestTrade {
  entry_date: string;
  entry_price: number;
  exit_date: string;
  exit_price: number;
  return_pct: number;
  days_held: number;
}

export interface BacktestResult {
  ticker: string;
  strategy_id: string;
  strategy_name: string;
  strategy_description: string;
  params: Record<string, number>;
  start_date: string;
  end_date: string;
  equity_curve: Array<{ date: string; equity: number; benchmark: number; position: number }>;
  metrics: BacktestMetrics;
  benchmark_metrics: BacktestMetrics;
  trades: BacktestTrade[];
}

// ------------------------------------------------------------------
// Portfolio optimization types
// ------------------------------------------------------------------

export interface OptimizeMethodDef {
  id: string;
  name: string;
  description: string;
  uses_conviction: boolean;
  uses_returns: boolean;
  category: "baseline" | "signal" | "optimization" | "risk";
}

export interface PortfolioMetrics {
  expected_return: number;
  volatility: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  calmar: number;
  total_return: number;
  hhi_concentration: number;
  effective_n: number;
  diversification_ratio: number;
  n_bars: number;
  equity_curve: Array<{ date: string; equity: number }>;
}

export interface OptimizeAsset {
  ticker: string;
  weight: number;
  expected_return: number;
  volatility: number;
  conviction: number | null;
}

export interface OptimizeResult {
  method_id: string;
  method_name: string;
  method_description: string;
  start_date: string;
  end_date: string;
  n_bars: number;
  assets: OptimizeAsset[];
  metrics: PortfolioMetrics;
  equal_weight_metrics: PortfolioMetrics;
  excluded_tickers: string[];
}

// ------------------------------------------------------------------
// API methods
// ------------------------------------------------------------------


// --- Plan pipeline ---

export interface PlanNodeSpec {
  id: string;
  metric: string;
  params: Record<string, unknown>;
  depends_on: string[];
  why: string;
}

export interface PlanClarification {
  id: string;
  question: string;
  options: string[];
  recommended: string;
  affects: string[];
  answer: string | null;
  effective: string;
  answered: boolean;
}

export interface ExecutedNode {
  node_id: string;
  metric: string;
  status: "ok" | "error" | "skipped";
  values: Record<string, unknown>;
  cached: boolean;
  error?: string;
  why?: string;
}

export interface HarnessOverride {
  field: string;
  model_said: unknown;
  harness_used: unknown;
  source: string;
}

export interface VerifiedClaim {
  metric: string;
  stated: number;
  actual?: number;
  verdict: "verified" | "mismatch" | "unverifiable";
  excerpt: string;
  unit?: string;
  delta_pct?: number;
  note?: string;
}

export interface Verification {
  status: "clean" | "mismatch" | "no_claims";
  checked: number;
  verified: number;
  mismatched: number;
  unverifiable: number;
  claims: VerifiedClaim[];
  messages: string[];
}

export interface PlanResult {
  ticker: string;
  conviction: number | null;
  stance: string | null;
  analysis: string | null;
  ai_full?: Record<string, unknown>;
  evaluation?: { notes?: string[]; narrative_grounded?: boolean };
  verification?: Verification;
  plan?: { question: string; nodes: PlanNodeSpec[]; clarifications: PlanClarification[] };
  execution?: {
    plan_hash: string;
    snapshot_sha256: string;
    nodes: ExecutedNode[];
    facts: Record<string, unknown>;
    ok_count: number;
    error_count: number;
    skipped_count: number;
    cache_hits: number;
    elapsed_ms: number;
  };
  clarifications_pending?: PlanClarification[];
  harness_overrides?: HarnessOverride[];
  ai_model?: string;
  planner_model?: string;
  run_uid?: string;
  ai_error?: { error: string; message: string };
  data_quality?: { providers_used: string[]; warning_count: number; warnings: string[] };
}

export interface MetricSignature {
  metric: string;
  label: string;
  tier: string;
  description: string;
  params: { name: string; type: string; description: string; default?: unknown }[];
  outputs: { name: string; type: string; description: string; unit?: string }[];
  notes?: string;
}


// --- Setup ---

export interface SetupKey {
  env: string;
  label: string;
  unlocks: string;
  signup: string;
  free_tier: boolean;
  secret: boolean;
  /** Whether a value is present. The value itself is never sent to the client. */
  configured: boolean;
  provider: string | null;
  provider_available: boolean | null;
  categories: string[];
}

export interface SetupInfo {
  keys: SetupKey[];
  providers: { name: string; available: boolean; categories: string[]; priority: number }[];
  summary: {
    providers_working: number;
    providers_total: number;
    keys_configured: number;
    keys_total: number;
    usable_without_keys: boolean;
  };
  llm: {
    provider: string;
    model: string;
    base_url: string;
    num_ctx: number;
    temperature: number;
    seed: number;
    thinking_disabled: boolean;
  };
  env_path: string;
}

// --- Autoresearch ---

export interface ExperimentWindow {
  label: string;
  start: string;
  end: string;
  observations: number;
  total_return_pct: number | null;
  annualized_return_pct: number | null;
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  max_drawdown_pct: number | null;
  win_rate_pct: number | null;
  trades: number | null;
  time_in_market_pct: number | null;
}

export interface ExperimentRow {
  id: number;
  run_tag: string;
  seq: number;
  ticker: string;
  strategy_id: string;
  params: Record<string, unknown> | null;
  hypothesis: string | null;
  is_baseline: boolean;
  kept: boolean;
  verdict: string;
  in_sample: ExperimentWindow | null;
  out_of_sample: ExperimentWindow | null;
  primary_metric: number | null;
  edge_vs_baseline: number | null;
  degradation: number | null;
  hurdle: number | null;
  overfit_flag: boolean;
  notes: string[] | null;
  reasoning: string | null;
  error: string | null;
  created_at: string | null;
}

export interface RunSummary {
  run_tag: string;
  experiments: number;
  trials: number;
  kept: number;
  discarded: number;
  errors: number;
  overfit_flagged: number;
  best: ExperimentRow | null;
  running?: boolean;
  harness?: Record<string, unknown>;
}


// --- Decisions ---

export interface SizingAssessment {
  ticker: string;
  proposed_value: number;
  currency: string;
  portfolio_value_before: number;
  cash_before: number;
  cash_after: number;
  funded_by_cash: boolean;
  existing_weight_pct: number | null;
  proposed_weight_pct: number | null;
  rank_after: number | null;
  holdings_after: number | null;
  concentration_top3_before_pct: number | null;
  concentration_top3_after_pct: number | null;
  correlation_to_book: number | null;
  overlap_observations: number | null;
  candidate_volatility_pct: number | null;
  portfolio_volatility_before_pct: number | null;
  portfolio_volatility_after_pct: number | null;
  volatility_change_pct: number | null;
  diversifying: boolean | null;
  flags: string[];
  notes: string[];
}

export interface DecisionRow {
  id: number;
  ticker: string;
  action: string;
  status: string;
  conviction: number | null;
  stance: string | null;
  rationale: string | null;
  proposed_value: number | null;
  proposed_weight_pct: number | null;
  price_at_decision: number | null;
  sizing: SizingAssessment | null;
  portfolio_context: { total_value?: number; holdings?: { ticker: string; weight_pct: number }[] } | null;
  research_run_uid: string | null;
  review_note: string | null;
  created_at: string | null;
  outcome?: {
    scored: boolean;
    move_pct?: number;
    in_your_favour_pct?: number;
    current_price?: number;
  };
}

/** One multiple's implied value range for the subject. */
export type CompsBand = {
  metric: string;
  label: string;
  low: number;
  mid: number;
  high: number;
  peer_count: number;
  subject_multiple: number;
  /** The per-share quantity recovered from the subject's own multiple. */
  per_share: number;
  peer_multiple: { low: number; mid: number; high: number };
  /** False when the subject's multiple is too far from the peer set to compare. */
  applicable: boolean;
  note: string | null;
};

export type CompsRange = {
  ticker: string;
  price: number | null;
  /** "curated" when the peer set was hand-picked, "sic" when inherited. */
  basis: string;
  vetted: boolean;
  as_of: string | null;
  peers: string[];
  bands: CompsBand[];
  dropped: { metric: string; reason: string; usable_peers: number }[];
  summary: {
    available: boolean;
    reason?: string;
    low?: number;
    mid?: number;
    high?: number;
    price?: number;
    position?: string;
    upside_to_mid_pct?: number;
    methods?: number;
    excluded?: string[];
    inapplicable?: string[];
  };
};

export type CostOfCapital = {
  cost_of_equity_pct: number | null;
  cost_of_debt_after_tax_pct: number | null;
  wacc_pct: number | null;
  steps: string[];
  missing: string[];
  inputs: Record<string, unknown>;
};

export type Intrinsic =
  | {
      ticker: string;
      available: false;
      reason: string;
      /** Drivers that could not be derived and must be supplied. */
      missing: string[];
      cost_of_capital: CostOfCapital;
      notes?: string[];
    }
  | {
      ticker: string;
      name?: string | null;
      available: true;
      price: number | null;
      base_case: {
        value_per_share: number;
        terminal_share_of_value: number;
        inputs: Record<string, number | null>;
        years: Record<string, number>[];
      };
      distribution: {
        runs: number;
        rejected: number;
        seed: number;
        percentiles: Record<string, number>;
        histogram: { from: number; to: number; count: number }[];
        price?: number;
        probability_value_above_price?: number;
        median_upside_pct?: number;
        independence_note: string;
      };
      cost_of_capital: CostOfCapital;
      cost_of_capital_note: string;
      driver_notes: string[];
    };

export type ConvictionLeg = {
  key: "fair_price" | "correction" | "horizon";
  label: string;
  claim: string;
  score: number | null;
  detail: Record<string, unknown>;
  open_questions: string[];
};

export type ConvictionChain = {
  ticker: string;
  legs: ConvictionLeg[];
  margin_of_safety: { value_pct: number | null; source: string };
  edge_sources_available: string[];
} & (
  | { available: false; reason: string; open_questions: string[]; unanswered: string[] }
  | {
      available: true;
      score: number;
      raw_product: number;
      label: string;
      weakest_leg: string;
      structure: { allowed: string; because: string };
      humility: { recent_wins: number; haircut: number; note: string };
    }
);

export const api = {
  health: () => fetchJSON<{ status: string }>("/health"),

  // --- Runs ---

  getRuns: (ticker?: string, limit = 20) =>
    fetchJSON<{ count: number; runs: { run_uid: string; ticker: string; mode: string; output?: { conviction_score?: number; stance?: string }; created_at: string }[] }>(
      `/runs?limit=${limit}${ticker ? `&ticker=${encodeURIComponent(ticker)}` : ""}`
    ),

  // --- Decisions ---

  sizePosition: (body: { ticker: string; amount?: number; weight_pct?: number }) =>
    postJSON<{ assessment: SizingAssessment; portfolio: Record<string, unknown> }>(
      "/decisions/size",
      body
    ),

  recordDecision: (body: {
    ticker: string;
    action: string;
    rationale?: string;
    conviction?: number;
    stance?: string;
    amount?: number;
    research_run_uid?: string;
  }) => postJSON<DecisionRow>("/decisions", body),

  getDecisions: (ticker?: string, limit = 100) =>
    fetchJSON<{ count: number; decisions: DecisionRow[] }>(
      `/decisions?limit=${limit}${ticker ? `&ticker=${encodeURIComponent(ticker)}` : ""}`
    ),

  // --- Setup ---

  getSetup: () => fetchJSON<SetupInfo>("/setup"),

  saveKeys: (updates: { env: string; value: string }[]) =>
    postJSON<{ ok: boolean; written: string[]; restart_required: boolean }>("/setup/keys", {
      updates,
    }),

  // --- Autoresearch ---

  getHarness: () => fetchJSON<Record<string, unknown>>("/autoresearch/harness"),

  getExperiments: (runTag?: string, limit = 100) =>
    fetchJSON<{ count: number; experiments: ExperimentRow[] }>(
      `/autoresearch/experiments?limit=${limit}${runTag ? `&run_tag=${encodeURIComponent(runTag)}` : ""}`
    ),

  getRunSummary: (runTag: string) =>
    fetchJSON<RunSummary>(`/autoresearch/summary/${encodeURIComponent(runTag)}`),

  getLoopStatus: () => fetchJSON<{ running: string[]; busy: boolean }>("/autoresearch/status"),

  startLoop: (body: {
    run_tag: string;
    tickers: string[];
    experiments?: number;
    days?: number;
  }) => postJSON<{ started: boolean; run_tag: string; poll: string }>("/autoresearch/run", body),

  // --- Plan pipeline ---

  getMetricCatalog: () =>
    fetchJSON<{ count: number; tiers: string[]; metrics: MetricSignature[] }>(
      "/research/metrics"
    ),

  runPlan: (body: {
    ticker: string;
    question?: string;
    style?: string;
    clarification_answers?: Record<string, string>;
    plan_override?: unknown;
  }) => postJSON<PlanResult>("/research/plan", body),


  // --- Original 5 data endpoints ---

  getPrice: (ticker: string, days = 365) =>
    fetchJSON<{ ticker: string; count: number; data: Record<string, unknown>[] }>(
      `/data/price/${ticker}?days=${days}`
    ),

  getFundamentals: (ticker: string) =>
    fetchJSON<Record<string, unknown>>(`/data/fundamentals/${ticker}`),

  // --- Valuation ---

  getCompsRange: (ticker: string) =>
    fetchJSON<CompsRange>(`/valuation/comps/${encodeURIComponent(ticker)}`),

  getConviction: (ticker: string, params: Record<string, string | number | boolean | undefined> = {}) => {
    const q = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
      .join("&");
    return fetchJSON<ConvictionChain>(
      `/valuation/conviction/${encodeURIComponent(ticker)}${q ? `?${q}` : ""}`
    );
  },

  getIntrinsic: (ticker: string, params: Record<string, string | number | undefined> = {}) => {
    const q = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
      .join("&");
    return fetchJSON<Intrinsic>(
      `/valuation/intrinsic/${encodeURIComponent(ticker)}${q ? `?${q}` : ""}`
    );
  },

  getTechnicals: (ticker: string) =>
    fetchJSON<Record<string, unknown>>(`/data/technicals/${ticker}`),

  getMacro: (series: string, days = 1825) =>
    fetchJSON<{ series: string; data: Record<string, unknown>[] }>(
      `/data/macro/${series}?days=${days}`
    ),

  getNews: (query: string, limit = 10) =>
    fetchJSON<{ articles: Record<string, unknown>[] }>(
      `/data/news?q=${encodeURIComponent(query)}&limit=${limit}`
    ),

  // --- New data endpoints (13) ---

  getESG: (ticker: string) =>
    fetchJSON<ESGScores>(`/data/esg/${ticker}`),

  getInsider: (ticker: string) =>
    fetchJSON<{ ticker: string; transactions: InsiderTransaction[] }>(
      `/data/insider/${ticker}`
    ),

  getInstitutional: (ticker: string) =>
    fetchJSON<{ ticker: string; holders: InstitutionalHolder[] }>(
      `/data/institutional/${ticker}`
    ),

  getEarnings: (ticker: string) =>
    fetchJSON<EarningsInfo>(`/data/earnings/${ticker}`),

  getAnalyst: (ticker: string) =>
    fetchJSON<AnalystRating>(`/data/analyst/${ticker}`),

  getSentiment: (ticker: string) =>
    fetchJSON<NewsSentiment>(`/data/sentiment/${ticker}`),

  getSectorPerformance: () =>
    fetchJSON<SectorPerformance>("/data/sector-performance"),

  getFamaFrench: () =>
    fetchJSON<FamaFrenchFactors>("/data/fama-french"),

  getOptions: (ticker: string) =>
    fetchJSON<OptionsChain>(`/data/options/${ticker}`),

  getFilings: (ticker: string) =>
    fetchJSON<{ ticker: string; filings: SECFiling[] }>(
      `/data/filings/${ticker}`
    ),

  getCongressional: (ticker: string) =>
    fetchJSON<{ ticker: string; trades: CongressionalTrade[] }>(
      `/data/congressional/${ticker}`
    ),

  getPeers: (ticker: string) =>
    fetchJSON<PeerComparison>(`/data/peers/${ticker}`),

  getProviderStatus: () =>
    fetchJSON<{ providers: ProviderStatus[] }>("/data/providers/status"),

  /** Named ticker lists — edit `config/watchlists.json` on the server. */
  getWatchlists: () =>
    fetchJSON<Record<string, string[]>>("/data/watchlists"),

  // --- Backtest ---

  listStrategies: () =>
    fetchJSON<{ strategies: BacktestStrategyDef[] }>("/backtest/strategies"),

  runBacktest: (
    ticker: string,
    strategy: string,
    opts: { days?: number; fee_bps?: number } = {},
  ) => {
    const params = new URLSearchParams({ strategy });
    if (opts.days) params.set("days", String(opts.days));
    if (opts.fee_bps != null) params.set("fee_bps", String(opts.fee_bps));
    return fetchJSON<BacktestResult>(
      `/backtest/${ticker}?${params.toString()}`,
    );
  },

  // --- Portfolio optimization ---

  listOptimizeMethods: () =>
    fetchJSON<{ methods: OptimizeMethodDef[] }>("/optimize/methods"),

  optimizePortfolio: (body: {
    tickers: string[];
    method: string;
    days?: number;
    convictions?: Record<string, number>;
  }) => postJSON<OptimizeResult>("/optimize", body),

  /** Yartseva Multibagger screener (yfinance fundamentals). */
  runYartsevaScreener: (body: {
    tickers?: string[];
    watchlist_group?: string;
    universe?: string;
    max_symbols?: number;
  }) => postJSON<YartsevaScreenerResponse>("/screeners/yartseva", body),

  runAcquisitionCompounderScreener: (body: {
    tickers?: string[];
    watchlist_group?: string;
    universe?: string;
    max_symbols?: number;
  }) => postJSON<AcquisitionCompounderScreenerResponse>("/screeners/acquisition-compounder", body),

  /** Index universes (S&P 500, NASDAQ-100, …) for screeners. */
  getScreenerUniverses: () =>
    fetchJSON<{ universes: ScreenerUniverseMeta[] }>("/screeners/universes"),

  // --- Research ---

  getPersonas: () =>
    fetchJSON<{ personas: { id: string }[]; default_committee: string[] }>("/research/personas"),

  checkTicker: (
    ticker: string,
    opts: {
      includeAi?: boolean;
      committee?: boolean;
      persona?: string | null;
      committee_personas?: string[] | null;
    } = {}
  ) => {
    const {
      includeAi = false,
      committee = false,
      persona = null,
      committee_personas = null,
    } = opts;
    return postJSON<ResearchCheckResponse>("/research/check", {
      ticker,
      include_ai: includeAi,
      committee,
      persona: persona || undefined,
      committee_personas: committee_personas ?? undefined,
    });
  },

  // --- Portfolio (SQLite-backed) ---

  getPortfolio: () =>
    fetchJSON<{
      total_value: number;
      cash: number;
      cash_pct: number;
      currency: string;
      benchmark: string | null;
      holdings: Array<{
        ticker: string;
        shares: number;
        avg_cost: number;
        currency: string;
        current_price: number;
        market_value: number;
        pnl: number;
        pnl_pct: number;
        weight_pct: number;
      }>;
    }>("/portfolio"),

  getRisk: () =>
    fetchJSON<Record<string, unknown>>("/portfolio/risk"),

  getTransactions: (limit = 100) =>
    fetchJSON<{
      transactions: Array<{
        id: number;
        txn_type: string;
        ticker: string | null;
        shares: number | null;
        price_per_share: number | null;
        fee: number;
        cash_delta: number;
        note: string | null;
        executed_at: string;
        meta: Record<string, unknown> | null;
      }>;
    }>(`/portfolio/transactions?limit=${limit}`),

  portfolioBuy: (body: {
    ticker: string;
    shares: number;
    price_per_share: number;
    fee?: number;
    note?: string;
  }) => postJSON("/portfolio/buy", body),

  portfolioSell: (body: {
    ticker: string;
    shares: number;
    price_per_share: number;
    fee?: number;
    note?: string;
  }) => postJSON("/portfolio/sell", body),

  portfolioDeposit: (body: { amount: number; note?: string }) =>
    postJSON("/portfolio/cash/deposit", body),

  portfolioWithdraw: (body: { amount: number; note?: string }) =>
    postJSON("/portfolio/cash/withdraw", body),

  portfolioSplit: (body: {
    ticker: string;
    ratio: number;
    note?: string;
  }) => postJSON("/portfolio/corporate/split", body),

  portfolioDividend: (body: {
    ticker: string;
    dividend_per_share: number;
    note?: string;
  }) => postJSON("/portfolio/corporate/dividend", body),

  patchHolding: (ticker: string, body: { shares?: number; avg_cost?: number }) =>
    patchJSON(`/portfolio/holdings/${encodeURIComponent(ticker)}`, body),
};

/** FinBERT headline sentiment from /research/check (optional `uv add` sentiment extra on API). */
export interface FinBERTNewsSentimentMeta {
  enabled: boolean;
  reason?: string | null;
  model?: string | null;
  aggregate: {
    article_count: number;
    mean_signed: number | null;
    positive_ratio: number | null;
    negative_ratio: number | null;
    neutral_ratio: number | null;
  };
}

/** Parsed LLM research JSON (single persona, PM synthesis, or default analyst). */
export interface AiAnalysisBlock {
  conviction_score: number;
  stance: string;
  investment_thesis: string;
  bull_case: string;
  bear_case: string;
  key_risks: string[];
  time_horizon: string;
  confidence_in_data: number;
}

export type CommitteeEntry = {
  persona_id: string;
  analysis?: AiAnalysisBlock;
  error?: { error: string; message?: string };
  /**
   * Which round this view came from. Entries in `committee` are post-rebuttal
   * where one ran, so a card showing an opinion has to be able to say whether
   * the analyst arrived at it independently or after seeing the others.
   */
  round?: number;
  revised?: boolean;
  conviction_before?: number | null;
  conviction_after?: number | null;
  stance_before?: string | null;
  stance_after?: string | null;
};

export interface ResearchCheckResponse {
  ticker: string;
  price: Record<string, number>;
  fundamentals: Record<string, unknown>;
  technicals: Record<string, unknown>;
  news: Array<{
    title: string;
    date: string;
    sentiment_label?: string;
    sentiment_score?: number;
  }>;
  news_sentiment?: FinBERTNewsSentimentMeta;
  conviction: number | null;
  stance: string | null;
  analysis: string | null;
  ai_full?: AiAnalysisBlock;
  ai_error?: { error: string; message?: string };
  evaluation?: Record<string, unknown>;
  ai_model?: string | null;
  ai_usage?: { prompt_tokens: number | null; completion_tokens: number | null } | Record<string, unknown>;
  persona_id?: string | null;
  committee?: CommitteeEntry[] | null;
  synthesis?: Record<string, unknown> | null;
  /**
   * Present only when the committee split materially and was sent back for a
   * rebuttal round before synthesis. `committee` above is the *post*-rebuttal
   * view — the one the PM actually reconciled — so anything reporting spread
   * has to say whether it was reached first time or after a second look.
   */
  refinement?: CommitteeRefinement | null;
  committee_round1?: CommitteeEntry[] | null;
  dissent_round1?: Dissent | null;
  dissent?: Dissent | null;
}

export interface Dissent {
  responded: number;
  conviction_min?: number;
  conviction_max?: number;
  conviction_mean?: number;
  conviction_spread?: number;
  stances?: Record<string, number>;
  unanimous_stance?: boolean;
  material_disagreement?: boolean;
}

export interface CommitteeRefinement {
  triggered: boolean;
  enabled: boolean;
  /** One line naming what the committee split over. */
  reason: string | null;
  revised_personas?: string[];
  held_personas?: string[];
  failed_personas?: string[];
  conviction_spread_before?: number;
  conviction_spread_after?: number;
  resolved?: boolean;
  /** Everyone folding at once reads as deference, not consensus. */
  suspect_convergence?: boolean;
  note?: string;
}
