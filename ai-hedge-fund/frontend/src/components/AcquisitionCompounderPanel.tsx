import { useState, useMemo, useEffect, Fragment } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  api,
  type ScreenerUniverseMeta,
  type AcquisitionCompounderResultRow,
  type AcquisitionCompounderScreenerResponse,
} from "@/lib/api";

const FALLBACK_UNIVERSES: ScreenerUniverseMeta[] = [
  { id: "sp500", label: "S&P 500", description: "", approx_count: 503 },
  { id: "nasdaq100", label: "NASDAQ-100", description: "", approx_count: 100 },
  { id: "dow", label: "Dow Jones 30", description: "", approx_count: 30 },
  {
    id: "russell2000",
    label: "Russell 2000 (IWM)",
    description: "",
    approx_count: 2000,
  },
];

function tierClass(tier: string | null): string {
  switch (tier) {
    case "elite":
      return "text-accent-green";
    case "strong":
      return "text-blue-300";
    case "watch":
      return "text-amber-200";
    case "weak":
      return "text-gray-500";
    default:
      return "text-gray-500";
  }
}

function downloadJson(data: AcquisitionCompounderScreenerResponse) {
  const payload = {
    exported_at: new Date().toISOString(),
    source: "acquisition-compounder-panel",
    ...data,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  a.href = url;
  a.download = `acquisition-compounder-${stamp}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export function AcquisitionCompounderPanel() {
  const watchlists = useQuery({
    queryKey: ["watchlists"],
    queryFn: api.getWatchlists,
  });
  const universes = useQuery({
    queryKey: ["screener-universes"],
    queryFn: api.getScreenerUniverses,
  });
  const groups = useMemo(
    () => (watchlists.data ? Object.keys(watchlists.data) : []),
    [watchlists.data],
  );
  const indexList = universes.data?.universes?.length
    ? universes.data.universes
    : FALLBACK_UNIVERSES;
  const [selection, setSelection] = useState("wl:default");
  const [maxSymbols, setMaxSymbols] = useState(500);
  const [custom, setCustom] = useState("");
  const [last, setLast] =
    useState<AcquisitionCompounderScreenerResponse | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!groups.length) return;
    const m = /^wl:(.+)$/.exec(selection);
    if (m && !groups.includes(m[1]!)) {
      setSelection(`wl:${groups[0]!}`);
    }
  }, [groups, selection]);

  const run = useMutation({
    mutationFn: async () => {
      const trimmed = custom.trim();
      if (trimmed) {
        const tickers = trimmed
          .split(/[\s,]+/)
          .map((t) => t.trim().toUpperCase())
          .filter(Boolean);
        return api.runAcquisitionCompounderScreener({ tickers });
      }
      if (selection.startsWith("u:")) {
        const universe = selection.slice(2);
        return api.runAcquisitionCompounderScreener({
          universe,
          max_symbols: Math.min(5000, Math.max(1, maxSymbols)),
        });
      }
      const wl = selection.startsWith("wl:") ? selection.slice(3) : "default";
      return api.runAcquisitionCompounderScreener({ watchlist_group: wl });
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
        <div className="min-w-[18rem]">
          <label
            htmlFor="acq-universe"
            className="block text-xs text-gray-500 mb-1"
          >
            Universe
          </label>
          <select
            id="acq-universe"
            value={selection}
            onChange={(e) => setSelection(e.target.value)}
            disabled={!!custom.trim() || run.isPending}
            className="w-full bg-surface-elevated border border-border rounded-lg px-3 py-2 text-sm text-white"
            aria-label="Screening universe"
          >
            <optgroup label="Watchlists (config/watchlists.json)">
              {groups.map((g) => (
                <option key={`wl:${g}`} value={`wl:${g}`}>
                  {g}
                </option>
              ))}
            </optgroup>
            <optgroup label="US indices">
              {indexList.map((u) => (
                <option key={`u:${u.id}`} value={`u:${u.id}`}>
                  {u.label} (~{u.approx_count})
                </option>
              ))}
            </optgroup>
          </select>
        </div>
        {selection.startsWith("u:") && !custom.trim() && (
          <div>
            <label
              htmlFor="acq-max-symbols"
              className="block text-xs text-gray-500 mb-1"
            >
              Max symbols (cap)
            </label>
            <input
              id="acq-max-symbols"
              type="number"
              min={1}
              max={5000}
              value={maxSymbols}
              onChange={(e) => setMaxSymbols(Number(e.target.value) || 500)}
              disabled={run.isPending}
              className="w-28 bg-surface-elevated border border-border rounded-lg px-3 py-2 text-sm text-white font-mono"
              aria-label="Maximum symbols to screen from index"
            />
          </div>
        )}
        <div className="grow min-w-[200px] max-w-xl">
          <label className="block text-xs text-gray-500 mb-1">
            Or paste tickers (overrides universe)
          </label>
          <input
            type="text"
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            placeholder="e.g. MSFT V RTX (space or comma separated)"
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
          <p className="text-xs uppercase tracking-wider text-gray-500 mb-1">
            Methodology
          </p>
          <p>{last.methodology_note}</p>
        </div>
      )}

      {last && (
        <div className="bg-surface-card rounded-xl border border-border/60 overflow-hidden">
          <div className="px-5 py-3 border-b border-border/60 flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-medium text-gray-300">Results</span>
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-xs text-gray-600">
                {last.count} ticker(s)
                {last.watchlist_group != null
                  ? ` · watchlist: ${last.watchlist_group}`
                  : ""}
                {last.universe != null ? (
                  <>
                    {" "}
                    · index: {last.universe}
                    {last.universe_total != null
                      ? ` (${last.tickers.length} of ${last.universe_total})`
                      : ""}
                    {last.universe_truncated
                      ? " — truncated to max_symbols"
                      : ""}
                  </>
                ) : null}
              </span>
              <button
                type="button"
                onClick={() => downloadJson(last)}
                className="text-xs px-2.5 py-1 rounded-lg border border-border text-gray-300 hover:bg-surface-elevated"
              >
                Export JSON
              </button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[1020px]">
              <thead>
                <tr className="text-gray-500 text-xs uppercase tracking-wider border-b border-border">
                  <th
                    className="py-3 pl-2 pr-1 w-8 font-medium"
                    aria-label="Expand"
                  />
                  <th className="py-3 px-5 font-medium">Ticker</th>
                  <th className="py-3 pr-3 font-medium">Stage 1</th>
                  <th className="py-3 pr-3 font-medium">Tier 2</th>
                  <th className="py-3 pr-3 font-medium">Score /45</th>
                  <th className="py-3 pr-3 font-medium">Tier</th>
                  <th className="py-3 pr-4 font-medium">Red flags</th>
                  <th className="py-3 pr-4 font-medium">Failures / error</th>
                </tr>
              </thead>
              <tbody>
                {last.results.map((r: AcquisitionCompounderResultRow) => (
                  <Fragment key={r.ticker}>
                    <tr className="border-b border-border/50 text-sm">
                      <td className="py-3 pl-2 pr-1 align-top">
                        <button
                          type="button"
                          onClick={() => toggleExpand(r.ticker)}
                          className="text-gray-500 hover:text-gray-300 text-xs px-1"
                          aria-expanded={expanded.has(r.ticker)}
                          title={
                            expanded.has(r.ticker)
                              ? "Hide details"
                              : "Show details"
                          }
                        >
                          {expanded.has(r.ticker) ? "▼" : "▶"}
                        </button>
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold">
                        <Link
                          to={`/research/${r.ticker}`}
                          className="text-blue-400 hover:underline"
                        >
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
                      <td className="py-3 pr-3">
                        {r.tier2_passed ? (
                          <span className="text-accent-green">Yes</span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-3 pr-3 font-mono text-white">
                        {r.total_score != null ? r.total_score.toFixed(1) : "—"}
                      </td>
                      <td
                        className={`py-3 pr-3 capitalize ${tierClass(r.tier)}`}
                      >
                        {r.tier ?? "—"}
                      </td>
                      <td className="py-3 pr-4 text-xs text-amber-200/90 max-w-[14rem]">
                        {r.red_flags?.length ? r.red_flags.join(", ") : "—"}
                      </td>
                      <td className="py-3 pr-4 text-xs text-gray-500 max-w-xs">
                        {r.error && (
                          <span className="text-amber-200">{r.error} · </span>
                        )}
                        {r.stage1_failures?.length
                          ? r.stage1_failures.join(", ")
                          : "—"}
                      </td>
                    </tr>
                    {expanded.has(r.ticker) && (
                      <tr className="border-b border-border/50 bg-black/25">
                        <td colSpan={8} className="px-5 py-4">
                          <div className="grid gap-4 md:grid-cols-2">
                            <div>
                              <p className="text-xs uppercase tracking-wider text-gray-500 mb-2">
                                9-factor scores (1–5)
                              </p>
                              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                                {Object.entries(r.scores ?? {}).map(
                                  ([k, v]) => (
                                    <Fragment key={k}>
                                      <dt className="text-gray-500">
                                        {k.replace(/_/g, " ")}
                                      </dt>
                                      <dd className="font-mono text-gray-200">
                                        {v}
                                      </dd>
                                    </Fragment>
                                  ),
                                )}
                              </dl>
                            </div>
                            <div>
                              <p className="text-xs uppercase tracking-wider text-gray-500 mb-2">
                                Industry
                              </p>
                              <p className="text-sm text-gray-400">
                                Prefer match:{" "}
                                {r.industry_prefer_match ? "yes" : "no"} · Avoid
                                list hit: {r.industry_avoid ? "yes" : "no"}
                              </p>
                            </div>
                          </div>
                          <div className="mt-4">
                            <p className="text-xs uppercase tracking-wider text-gray-500 mb-2">
                              Snapshot (yfinance)
                            </p>
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
          Choose a watchlist or enter tickers, then run. Large lists may take a
          while (one yfinance fetch per symbol).
        </p>
      )}
    </div>
  );
}
