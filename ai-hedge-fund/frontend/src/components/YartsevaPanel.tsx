import { useState, useMemo, useEffect, Fragment } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type YartsevaResultRow, type YartsevaScreenerResponse } from "@/lib/api";

function tierLabel(tier: string | null): string {
  switch (tier) {
    case "strong":
      return "Strong (75+)";
    case "watch":
      return "Watch (55–74)";
    case "borderline":
      return "Borderline (35–54)";
    case "fail":
      return "Fail (<35)";
    default:
      return "—";
  }
}

function tierClass(tier: string | null): string {
  switch (tier) {
    case "strong":
      return "text-accent-green";
    case "watch":
      return "text-blue-300";
    case "borderline":
      return "text-amber-200";
    case "fail":
      return "text-gray-500";
    default:
      return "text-gray-500";
  }
}

function fmtNum(v: number | null | undefined, decimals = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(decimals);
}

function downloadYartsevaJson(data: YartsevaScreenerResponse) {
  const payload = {
    exported_at: new Date().toISOString(),
    source: "yartseva-panel",
    ...data,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  a.href = url;
  a.download = `yartseva-screener-${stamp}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export function YartsevaPanel() {
  const watchlists = useQuery({ queryKey: ["watchlists"], queryFn: api.getWatchlists });
  const groups = useMemo(
    () => (watchlists.data ? Object.keys(watchlists.data) : []),
    [watchlists.data],
  );
  const [group, setGroup] = useState("default");
  const [custom, setCustom] = useState("");
  const [last, setLast] = useState<YartsevaScreenerResponse | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (groups.length && !groups.includes(group)) {
      setGroup(groups[0]!);
    }
  }, [groups, group]);

  const run = useMutation({
    mutationFn: async () => {
      const trimmed = custom.trim();
      if (trimmed) {
        const tickers = trimmed
          .split(/[\s,]+/)
          .map((t) => t.trim().toUpperCase())
          .filter(Boolean);
        return api.runYartsevaScreener({ tickers });
      }
      return api.runYartsevaScreener({ watchlist_group: group });
    },
    onSuccess: (data) => {
      setLast(data);
      setExpanded(new Set());
    },
  });

  const toggleExpand = (ticker: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Watchlist group</label>
          <select
            value={group}
            onChange={(e) => setGroup(e.target.value)}
            disabled={!!custom.trim() || run.isPending}
            className="bg-surface-elevated border border-border rounded-lg px-3 py-2 text-sm text-white"
          >
            {groups.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </div>
        <div className="grow min-w-[200px] max-w-xl">
          <label className="block text-xs text-gray-500 mb-1">
            Or paste tickers (overrides group)
          </label>
          <input
            type="text"
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            placeholder="e.g. SIGA PLAY (space or comma separated)"
            className="w-full bg-surface-elevated border border-border rounded-lg px-3 py-2 text-sm text-white placeholder:text-gray-600"
          />
        </div>
        <button
          type="button"
          disabled={run.isPending}
          onClick={() => run.mutate()}
          className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium disabled:opacity-50"
        >
          {run.isPending ? "Running…" : "Run screener"}
        </button>
      </div>

      {run.isError && (
        <p className="text-sm text-red-400">{(run.error as Error).message}</p>
      )}

      {last && (
        <div className="rounded-xl border border-border/60 bg-surface-card/50 p-4 text-sm text-gray-400">
          <p className="text-xs uppercase tracking-wider text-gray-500 mb-1">Macro regime (portfolio-level)</p>
          <p>{last.macro_regime_note}</p>
        </div>
      )}

      {last && (
        <div className="bg-surface-card rounded-xl border border-border/60 overflow-hidden">
          <div className="px-5 py-3 border-b border-border/60 flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-medium text-gray-300">Results</span>
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-600">
                {last.count} ticker(s)
                {last.watchlist_group ? ` · ${last.watchlist_group}` : ""}
              </span>
              <button
                type="button"
                onClick={() => downloadYartsevaJson(last)}
                className="text-xs px-2.5 py-1 rounded-lg border border-border text-gray-300 hover:bg-surface-elevated"
              >
                Export JSON
              </button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[960px]">
              <thead>
                <tr className="text-gray-500 text-xs uppercase tracking-wider border-b border-border">
                  <th className="py-3 pl-2 pr-1 w-8 font-medium" aria-label="Expand" />
                  <th className="py-3 px-5 font-medium">Ticker</th>
                  <th className="py-3 pr-3 font-medium">Stage 1</th>
                  <th className="py-3 pr-3 font-medium">Composite</th>
                  <th className="py-3 pr-3 font-medium">Tier</th>
                  <th className="py-3 pr-3 font-medium">Short flag</th>
                  <th className="py-3 pr-4 font-medium">Sub-scores</th>
                  <th className="py-3 pr-4 font-medium">Failures / error</th>
                </tr>
              </thead>
              <tbody>
                {last.results.map((r: YartsevaResultRow) => (
                  <Fragment key={r.ticker}>
                    <tr className="border-b border-border/50 text-sm">
                      <td className="py-3 pl-2 pr-1 align-top">
                        <button
                          type="button"
                          onClick={() => toggleExpand(r.ticker)}
                          className="text-gray-500 hover:text-gray-300 text-xs px-1"
                          aria-expanded={expanded.has(r.ticker)}
                          title={expanded.has(r.ticker) ? "Hide details" : "Show details"}
                        >
                          {expanded.has(r.ticker) ? "▼" : "▶"}
                        </button>
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold">
                        <Link to={`/research/${r.ticker}`} className="text-blue-400 hover:underline">
                          {r.ticker}
                        </Link>
                      </td>
                      <td className="py-3 pr-3">
                        {r.stage1_passed ? (
                          <span className="text-accent-green">Pass</span>
                        ) : (
                          <span className="text-gray-500">Fail</span>
                        )}
                      </td>
                      <td className="py-3 pr-3 font-mono text-white">
                        {r.composite != null ? r.composite.toFixed(2) : "—"}
                      </td>
                      <td className={`py-3 pr-3 ${tierClass(r.tier)}`}>{tierLabel(r.tier)}</td>
                      <td className="py-3 pr-3">
                        {r.short_sell_flag ? <span className="text-amber-300">Yes</span> : "—"}
                      </td>
                      <td className="py-3 pr-4 text-xs text-gray-400 font-mono max-w-[22rem]">
                        {r.stage1_passed ? (
                          <>
                            FCF {r.fcf_yield_score?.toFixed(0) ?? "—"} · V {r.value_score?.toFixed(0) ?? "—"} · P{" "}
                            {r.profitability_score?.toFixed(0) ?? "—"} · IQ{" "}
                            {r.investment_quality_score?.toFixed(0) ?? "—"} · Sz {r.size_score?.toFixed(0) ?? "—"} · En{" "}
                            {r.entry_timing_score?.toFixed(0) ?? "—"}
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-3 pr-4 text-xs text-gray-500 max-w-xs">
                        {r.error && <span className="text-amber-200">{r.error} · </span>}
                        {r.stage1_failures?.length ? r.stage1_failures.join(", ") : "—"}
                      </td>
                    </tr>
                    {expanded.has(r.ticker) && (
                      <tr className="border-b border-border/50 bg-black/25">
                        <td colSpan={8} className="px-5 py-4">
                          <div className="grid gap-4 md:grid-cols-2">
                            <div>
                              <p className="text-xs uppercase tracking-wider text-gray-500 mb-2">Stage 2 scores (0–100)</p>
                              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                                <dt className="text-gray-500">FCF yield (30%)</dt>
                                <dd className="font-mono text-gray-200">{fmtNum(r.fcf_yield_score, 1)}</dd>
                                <dt className="text-gray-500">Value (25%)</dt>
                                <dd className="font-mono text-gray-200">{fmtNum(r.value_score, 1)}</dd>
                                <dt className="text-gray-500">Profitability (15%)</dt>
                                <dd className="font-mono text-gray-200">{fmtNum(r.profitability_score, 1)}</dd>
                                <dt className="text-gray-500">Investment quality (15%)</dt>
                                <dd className="font-mono text-gray-200">{fmtNum(r.investment_quality_score, 1)}</dd>
                                <dt className="text-gray-500">Size (10%)</dt>
                                <dd className="font-mono text-gray-200">{fmtNum(r.size_score, 1)}</dd>
                                <dt className="text-gray-500">Entry timing (5%)</dt>
                                <dd className="font-mono text-gray-200">{fmtNum(r.entry_timing_score, 1)}</dd>
                              </dl>
                            </div>
                            <div>
                              <p className="text-xs uppercase tracking-wider text-gray-500 mb-2">Drivers & ratios</p>
                              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                                <dt className="text-gray-500">FCF yield %</dt>
                                <dd className="font-mono text-gray-200">{fmtNum(r.fcf_yield_pct, 2)}</dd>
                                <dt className="text-gray-500">Book / market</dt>
                                <dd className="font-mono text-gray-200">{fmtNum(r.book_to_market, 3)}</dd>
                                <dt className="text-gray-500">ROA %</dt>
                                <dd className="font-mono text-gray-200">{fmtNum(r.roa_pct, 2)}</dd>
                                <dt className="text-gray-500">Asset growth % (YoY)</dt>
                                <dd className="font-mono text-gray-200">{fmtNum(r.asset_growth_pct, 2)}</dd>
                                <dt className="text-gray-500">EBITDA growth % (TTM vs prior)</dt>
                                <dd className="font-mono text-gray-200">{fmtNum(r.ebitda_growth_pct, 2)}</dd>
                                <dt className="text-gray-500">Inv excess (pp)</dt>
                                <dd className="font-mono text-gray-200">{fmtNum(r.inv_excess_pp, 2)}</dd>
                                <dt className="text-gray-500">52w range position %</dt>
                                <dd className="font-mono text-gray-200">{fmtNum(r.entry_range_pct, 2)}</dd>
                              </dl>
                            </div>
                          </div>
                          <div className="mt-4">
                            <p className="text-xs uppercase tracking-wider text-gray-500 mb-2">Raw snapshot (yfinance)</p>
                            <pre className="text-xs font-mono text-gray-400 bg-black/50 rounded-lg p-3 overflow-x-auto max-h-64 overflow-y-auto border border-border/60">
                              {JSON.stringify(r.snapshot ?? {}, null, 2)}
                            </pre>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!last && !run.isPending && (
        <p className="text-sm text-gray-500">
          Choose a watchlist or enter tickers, then run. Large lists may take a while (one yfinance fetch per
          symbol).
        </p>
      )}
    </div>
  );
}
