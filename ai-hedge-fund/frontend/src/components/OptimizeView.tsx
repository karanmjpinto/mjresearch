import { useState, useMemo, useEffect } from "react";
import { LookbackTimeline } from "./LookbackTimeline";
import { InfoTip } from "./InfoTip";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api, type OptimizeResult } from "@/lib/api";
import { AppNav } from "./AppNav";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";

const DEFAULT_TICKERS = "AAPL, MSFT, NVDA, GOOGL, META, AMZN";

// Palette from DESIGN.md — primary blue + semantic + info + muted neutral
const WEIGHT_COLORS = [
  "#3b82f6",
  "#22c55e",
  "#f59e0b",
  "#ef4444",
  "#38bdf8",
  "#a1a1aa",
  "#60a5fa",
  "#a3e635",
  "#fbbf24",
  "#f87171",
];

export function OptimizeView() {
  const [tickersText, setTickersText] = useState(DEFAULT_TICKERS);
  const [method, setMethod] = useState("hrp");
  const [days, setDays] = useState(730);
  const [useConviction, setUseConviction] = useState(false);
  const [convictions, setConvictions] = useState<Record<string, number>>({});
  const [watchlistGroup, setWatchlistGroup] = useState<string>("");

  const methods = useQuery({
    queryKey: ["optimize-methods"],
    queryFn: () => api.listOptimizeMethods(),
    staleTime: 60_000 * 60,
  });
  const watchlists = useQuery({
    queryKey: ["watchlists"],
    queryFn: api.getWatchlists,
  });

  const tickers = useMemo(
    () =>
      tickersText
        .split(/[,\s\n]+/)
        .map((t) => t.trim().toUpperCase())
        .filter(Boolean),
    [tickersText],
  );

  // Sync convictions dict keys with tickers (keep existing scores, default 50 for new)
  useEffect(() => {
    setConvictions((prev) => {
      const next: Record<string, number> = {};
      for (const t of tickers) next[t] = prev[t] ?? 50;
      return next;
    });
  }, [tickersText]); // eslint-disable-line react-hooks/exhaustive-deps

  const run = useMutation({
    mutationFn: () =>
      api.optimizePortfolio({
        tickers,
        method,
        days,
        convictions: useConviction ? convictions : undefined,
      }),
  });

  const selectedMethod = methods.data?.methods.find((m) => m.id === method);
  const convictionSupported = selectedMethod?.uses_conviction ?? false;
  const data: OptimizeResult | undefined = run.data;

  const pieData = useMemo(() => {
    if (!data) return [];
    return data.assets
      .filter((a) => a.weight > 0.001)
      .map((a) => ({ name: a.ticker, value: +(a.weight * 100).toFixed(2) }));
  }, [data]);

  const equityChart = useMemo(() => {
    if (!data) return [];
    const strat = data.metrics.equity_curve ?? [];
    const eq = data.equal_weight_metrics.equity_curve ?? [];
    const n = Math.min(strat.length, eq.length);
    const step = Math.max(1, Math.floor(n / 400));
    const out: Array<{ date: string; strategy: number; equal: number }> = [];
    for (let i = 0; i < n; i += step) {
      out.push({
        date: strat[i].date,
        strategy: +((strat[i].equity - 1) * 100).toFixed(2),
        equal: +((eq[i].equity - 1) * 100).toFixed(2),
      });
    }
    if (out[out.length - 1]?.date !== strat[n - 1]?.date && n > 0) {
      out.push({
        date: strat[n - 1].date,
        strategy: +((strat[n - 1].equity - 1) * 100).toFixed(2),
        equal: +((eq[n - 1].equity - 1) * 100).toFixed(2),
      });
    }
    return out;
  }, [data]);

  const applyWatchlist = (key: string) => {
    setWatchlistGroup(key);
    if (key && watchlists.data?.[key]) {
      setTickersText(watchlists.data[key].join(", "));
    }
  };

  return (
    <div className="flex flex-col h-screen">
      <AppNav active="optimize" />

      <div className="grow overflow-y-auto p-6">
        <div className="max-w-6xl mx-auto flex flex-col gap-5">
          <div>
            <h1 className="text-2xl font-bold text-white mb-1">
              Portfolio construction
            </h1>
            <p className="text-gray-500 text-sm">
              Given a basket and (optionally) AI conviction scores, compute
              weights via risk parity, Markowitz, or signal-driven methods.
              Returns are aligned on common dates; daily-rebalance metrics
              assume no slippage.
            </p>
          </div>

          {/* Controls card */}
          <div className="bg-surface-card rounded-xl p-5 flex flex-col gap-4 border border-border/60">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="md:col-span-2 flex flex-col gap-1.5">
                <label className="text-label uppercase tracking-wider text-gray-500">
                  Tickers (comma or space separated)
                </label>
                <textarea
                  value={tickersText}
                  onChange={(e) => setTickersText(e.target.value)}
                  rows={2}
                  className="bg-surface-elevated border border-border rounded px-3 py-2 text-sm text-white font-mono resize-none"
                  placeholder="AAPL, MSFT, NVDA, ..."
                />
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-label text-gray-600">
                    Load watchlist:
                  </span>
                  <select
                    value={watchlistGroup}
                    onChange={(e) => applyWatchlist(e.target.value)}
                    className="bg-surface-elevated border border-border rounded px-2 py-1 text-label text-white"
                  >
                    <option value="">—</option>
                    {watchlists.data &&
                      Object.keys(watchlists.data).map((k) => (
                        <option key={k} value={k}>
                          {k} ({watchlists.data![k].length})
                        </option>
                      ))}
                  </select>
                  <span className="text-label text-gray-500 ml-auto">
                    {tickers.length} tickers queued
                  </span>
                </div>
              </div>

              <div className="flex flex-col gap-3">
                <div>
                  <label className="text-label uppercase tracking-wider text-gray-500">
                    Method
                  </label>
                  <select
                    value={method}
                    onChange={(e) => setMethod(e.target.value)}
                    className="w-full mt-1 bg-surface-elevated border border-border rounded px-2 py-1.5 text-sm text-white"
                  >
                    {methods.data?.methods.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-label uppercase tracking-wider text-gray-500">
                    Window
                  </label>
                  <select
                    value={days}
                    onChange={(e) => setDays(+e.target.value)}
                    className="w-full mt-1 bg-surface-elevated border border-border rounded px-2 py-1.5 text-sm text-white"
                  >
                    <option value={365}>1 year</option>
                    <option value={730}>2 years</option>
                    <option value={1095}>3 years</option>
                    <option value={1825}>5 years</option>
                  </select>
                </div>
              </div>
            </div>

            {selectedMethod && (
              <div className="flex items-start gap-3 p-3 rounded border border-border/40 bg-black/20">
                <div className="flex-1">
                  <p className="text-xs font-semibold text-blue-400">
                    {selectedMethod.name}{" "}
                    <span className="text-label text-gray-600 font-normal ml-2 uppercase tracking-wider">
                      {selectedMethod.category}
                    </span>
                  </p>
                  <p className="text-xs text-gray-400 mt-1 leading-relaxed">
                    {selectedMethod.description}
                  </p>
                </div>
                {selectedMethod.uses_conviction && (
                  <label className="flex items-center gap-2 text-xs text-gray-300 shrink-0">
                    <input
                      type="checkbox"
                      checked={useConviction}
                      onChange={(e) => setUseConviction(e.target.checked)}
                    />
                    Use convictions
                  </label>
                )}
              </div>
            )}

            {/* Conviction sliders */}
            {useConviction && convictionSupported && tickers.length > 0 && (
              <div className="bg-black/20 rounded p-3 border border-border/40">
                <p className="text-label uppercase tracking-wider text-gray-500 mb-2">
                  AI conviction scores (0–100)
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                  {tickers.map((t) => (
                    <ConvictionRow
                      key={t}
                      ticker={t}
                      value={convictions[t] ?? 50}
                      onChange={(v) =>
                        setConvictions((prev) => ({ ...prev, [t]: v }))
                      }
                    />
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => run.mutate()}
                disabled={run.isPending || tickers.length < 2}
                className="px-5 py-2 bg-blue-500 hover:bg-blue-400 disabled:bg-gray-700 disabled:cursor-not-allowed text-white text-sm font-medium rounded transition-colors"
              >
                {run.isPending ? "Optimizing…" : "Build portfolio"}
              </button>
            </div>
          </div>

          {run.isError && (
            <div className="bg-amber-900/20 border border-amber-700/40 rounded-xl p-4 text-sm text-amber-200">
              {(run.error as Error).message}
            </div>
          )}

          {data && (
            <>
              {/* Metric cards */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <MetricCard
                  label="Expected return (ann)"
                  strategy={data.metrics.expected_return}
                  benchmark={data.equal_weight_metrics.expected_return}
                  fmt="pct"
                />
                <MetricCard
                  label="Volatility (ann)"
                  strategy={data.metrics.volatility}
                  benchmark={data.equal_weight_metrics.volatility}
                  fmt="pct"
                  higherIsBetter={false}
                />
                <MetricCard
                  label="Sharpe"
                  strategy={data.metrics.sharpe}
                  benchmark={data.equal_weight_metrics.sharpe}
                  fmt="num"
                />
                <MetricCard
                  label="Max drawdown"
                  strategy={data.metrics.max_drawdown}
                  benchmark={data.equal_weight_metrics.max_drawdown}
                  fmt="pct"
                />
                <MetricCard
                  label="Effective N"
                  strategy={data.metrics.effective_n}
                  benchmark={data.equal_weight_metrics.effective_n}
                  fmt="num"
                />
              </div>

              {/* Weights + Pie */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                <div className="lg:col-span-1 bg-surface-card rounded-xl p-4">
                  <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-2">
                    Allocation
                  </h3>
                  <div className="h-60">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={pieData}
                          dataKey="value"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          innerRadius={50}
                          outerRadius={90}
                          paddingAngle={1}
                          stroke="#121214"
                        >
                          {pieData.map((_, i) => (
                            <Cell
                              key={i}
                              fill={WEIGHT_COLORS[i % WEIGHT_COLORS.length]}
                            />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            background: "#121214",
                            border: "1px solid #27272a",
                            fontSize: 12,
                          }}
                          formatter={(v: number) => `${v.toFixed(2)}%`}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="text-label text-gray-600 mt-1 text-center">
                    {pieData.length} of {data.assets.length} assets have
                    non-zero weight
                  </p>
                </div>

                <div className="lg:col-span-2 bg-surface-card rounded-xl p-4">
                  <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">
                    Weights & per-asset stats
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-gray-500 border-b border-border">
                          <th className="text-left py-1.5"></th>
                          <th className="text-left py-1.5">Ticker</th>
                          <th className="text-right py-1.5">Weight</th>
                          <th className="text-right py-1.5">Exp. Return</th>
                          <th className="text-right py-1.5">Volatility</th>
                          {useConviction && convictionSupported && (
                            <th className="text-right py-1.5">Conviction</th>
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {data.assets.map((a) => (
                          <tr
                            key={a.ticker}
                            className="border-b border-border/50"
                          >
                            <td className="py-1.5">
                              <span
                                className="inline-block w-2.5 h-2.5 rounded-full"
                                style={{
                                  background:
                                    a.weight > 0.001
                                      ? (WEIGHT_COLORS[
                                          pieData.findIndex(
                                            (p) => p.name === a.ticker,
                                          ) % WEIGHT_COLORS.length
                                        ] ?? "#52525b")
                                      : "#27272a",
                                }}
                              />
                            </td>
                            <td className="py-1.5 font-mono text-gray-200">
                              {a.ticker}
                            </td>
                            <td className="text-right py-1.5 font-mono text-white font-semibold">
                              {(a.weight * 100).toFixed(2)}%
                            </td>
                            <td
                              className={`text-right py-1.5 font-mono ${
                                a.expected_return >= 0
                                  ? "text-accent-green"
                                  : "text-accent-red"
                              }`}
                            >
                              {(a.expected_return * 100).toFixed(1)}%
                            </td>
                            <td className="text-right py-1.5 font-mono text-gray-400">
                              {(a.volatility * 100).toFixed(1)}%
                            </td>
                            {useConviction && convictionSupported && (
                              <td className="text-right py-1.5 font-mono text-gray-300">
                                {a.conviction != null
                                  ? a.conviction.toFixed(0)
                                  : "—"}
                              </td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {data.excluded_tickers.length > 0 && (
                    <p className="text-label text-amber-300 mt-2">
                      Excluded (no price history):{" "}
                      {data.excluded_tickers.join(", ")}
                    </p>
                  )}
                </div>
              </div>

              {/* Equity curve */}
              <div className="bg-surface-card rounded-xl p-4">
                {/* The window, before the curve it produced. Every figure on
                  * this page is measured backwards over it, and that used to
                  * be the least visible thing on the screen — which is how a
                  * backtest gets read as a forecast. */}
                <div className="mb-4 border-b border-border pb-4">
                  <LookbackTimeline
                    start={data.start_date}
                    end={data.end_date}
                    bars={data.n_bars}
                    requestedDays={days}
                    purpose="Weights, expected returns, volatility and the curve below are all measured over this window, looking backwards. Nothing here is a forecast."
                  />
                </div>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="flex items-center gap-xs text-xs uppercase tracking-wider text-gray-500">
                    Simulated performance (daily rebalance)
                    <InfoTip term="lookback-window" />
                  </h3>
                </div>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={equityChart}
                      margin={{ top: 6, right: 8, left: 0, bottom: 0 }}
                    >
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
                          name === "strategy"
                            ? data.method_name
                            : "Equal weight",
                        ]}
                      />
                      <Legend
                        wrapperStyle={{ fontSize: 11 }}
                        iconType="plainline"
                        formatter={(v) =>
                          v === "strategy" ? data.method_name : "Equal weight"
                        }
                      />
                      <Line
                        type="monotone"
                        dataKey="equal"
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

              {/* Secondary stats */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <SmallStat
                  label="Total return"
                  value={`${(data.metrics.total_return * 100).toFixed(1)}%`}
                />
                <SmallStat
                  label="Sortino"
                  value={data.metrics.sortino.toFixed(2)}
                />
                <SmallStat
                  label="Calmar"
                  value={data.metrics.calmar.toFixed(2)}
                />
                <SmallStat
                  label="Diversification ratio"
                  value={data.metrics.diversification_ratio.toFixed(2)}
                />
                <SmallStat
                  label="HHI concentration"
                  value={data.metrics.hhi_concentration.toFixed(3)}
                />
                <SmallStat
                  label="Effective N"
                  value={data.metrics.effective_n.toFixed(2)}
                />
                <SmallStat label="Bars" value={String(data.metrics.n_bars)} />
                <SmallStat label="Assets" value={String(data.assets.length)} />
              </div>
            </>
          )}

          {!data && !run.isPending && (
            <div className="bg-surface-card rounded-xl p-10 text-center border border-dashed border-border/60">
              <p className="text-gray-500 text-sm">
                Pick tickers, a method, and optionally attach AI convictions —
                then <strong className="text-gray-300">Build portfolio</strong>.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------
// Sub-components
// ------------------------------------------------------------------

function ConvictionRow({
  ticker,
  value,
  onChange,
}: {
  ticker: string;
  value: number;
  onChange: (v: number) => void;
}) {
  const tier =
    value >= 70
      ? "text-emerald-400"
      : value >= 50
        ? "text-gray-300"
        : value >= 40
          ? "text-amber-300"
          : "text-red-400";
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-mono text-gray-400 w-14 shrink-0">
        {ticker}
      </span>
      <input
        type="range"
        min={0}
        max={100}
        value={value}
        onChange={(e) => onChange(+e.target.value)}
        className="flex-1 accent-blue-500"
      />
      <span className={`text-xs font-mono w-8 text-right ${tier}`}>
        {value}
      </span>
    </div>
  );
}

function MetricCard({
  label,
  strategy,
  benchmark,
  fmt,
  higherIsBetter = true,
}: {
  label: string;
  strategy: number;
  benchmark: number;
  fmt: "pct" | "num";
  higherIsBetter?: boolean;
}) {
  const fmtVal = (v: number) => {
    if (fmt === "pct") {
      const pct = v * 100;
      return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
    }
    return v.toFixed(2);
  };
  const beats = higherIsBetter ? strategy > benchmark : strategy < benchmark;
  return (
    <div className="bg-surface-card rounded-xl p-3 border border-border/60">
      <p className="text-label text-gray-500 uppercase tracking-wider">
        {label}
      </p>
      <p className="text-lg font-bold font-mono mt-1 text-white">
        {fmtVal(strategy)}
      </p>
      <div className="flex items-center justify-between text-label mt-1">
        <span className="text-gray-600">vs 1/N</span>
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
      <p className="text-label text-gray-500 uppercase tracking-wider">
        {label}
      </p>
      <p className="text-sm text-white font-mono mt-0.5">{value}</p>
    </div>
  );
}
