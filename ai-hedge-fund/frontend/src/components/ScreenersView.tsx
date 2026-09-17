import { useState } from "react";
import { Navigate, useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  DEFAULT_SCREENER_ID,
  SCREENER_VIEWS,
  getScreenerById,
  type ScreenerPlay,
} from "@/config/screeners";
import { api } from "@/lib/api";
import { AppNav } from "./AppNav";
import { PersonaOpinionGrid, humanizePersonaId } from "./PersonaOpinionCards";
import { YartsevaPanel } from "./YartsevaPanel";
import { AcquisitionCompounderPanel } from "./AcquisitionCompounderPanel";
import { ScreenResults } from "./ScreenResults";

function tickerLooksValid(t: string): boolean {
  const s = t.trim();
  if (!s || s === "—" || s === "-") return false;
  return /^[A-Z0-9.\-=]{1,32}$/i.test(s);
}

function PlayRow({
  p,
  expanded,
  onToggleViews,
}: {
  p: ScreenerPlay;
  expanded: boolean;
  onToggleViews: () => void;
}) {
  const canFetch = tickerLooksValid(p.ticker);
  const views = useQuery({
    queryKey: ["screener-committee", p.ticker],
    queryFn: () =>
      api.checkTicker(p.ticker, { includeAi: true, committee: true }),
    enabled: expanded && canFetch,
    staleTime: 120_000,
  });

  return (
    <>
      <tr className="border-b border-border/50 text-sm">
        <td className="py-3 pr-4 font-mono font-semibold text-white">
          {canFetch ? (
            <Link
              to={`/research/${p.ticker.toUpperCase()}`}
              className="text-blue-400 hover:underline"
            >
              {p.ticker}
            </Link>
          ) : (
            p.ticker
          )}
        </td>
        <td className="py-3 pr-4 text-gray-300 max-w-xs">{p.setup}</td>
        <td className="py-3 pr-4 text-gray-200 font-mono">{p.entry}</td>
        <td className="py-3 pr-4 text-gray-400 font-mono">{p.stop ?? "—"}</td>
        <td className="py-3 pr-4 text-gray-400 font-mono">{p.target ?? "—"}</td>
        <td className="py-3 pr-4 text-gray-300">
          {p.sizePct != null ? `${p.sizePct.toFixed(1)}% book` : "—"}
          {p.sizeNotes ? (
            <span className="block text-xs text-gray-500 mt-0.5">
              {p.sizeNotes}
            </span>
          ) : null}
        </td>
        <td className="py-3 pr-4 text-gray-500 text-xs max-w-[14rem]">
          {p.notes ?? "—"}
        </td>
        <td className="py-3 pr-2 text-right align-top">
          <button
            type="button"
            disabled={!canFetch}
            onClick={onToggleViews}
            className={`text-xs px-2 py-1 rounded-lg border transition-colors ${
              canFetch
                ? expanded
                  ? "bg-blue-500/20 text-blue-300 border-blue-500/40"
                  : "bg-surface-elevated text-gray-400 border-border hover:text-gray-200"
                : "opacity-40 cursor-not-allowed border-border text-gray-600"
            }`}
            title={
              canFetch
                ? "Load committee AI views (Ollama)"
                : "Set a valid ticker to load views"
            }
          >
            {expanded ? "Hide views" : "Investor views"}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-border/60 bg-black/20">
          <td colSpan={8} className="px-5 py-4">
            {!canFetch && (
              <p className="text-sm text-gray-500">
                Add a valid ticker symbol to load named investor opinions.
              </p>
            )}
            {canFetch && views.isLoading && (
              <p className="text-sm text-gray-400">
                Running committee analysis… (Ollama — may take a minute)
              </p>
            )}
            {canFetch && views.isError && (
              <p className="text-sm text-red-400">
                {(views.error as Error).message}
              </p>
            )}
            {canFetch && views.data?.ai_error && (
              <p className="text-sm text-amber-200">
                AI:{" "}
                {(views.data.ai_error as { message?: string }).message ??
                  views.data.ai_error.error}
              </p>
            )}
            {canFetch &&
              views.data?.committee &&
              views.data.committee.length > 0 && (
                <div className="flex flex-col gap-3">
                  <div className="flex flex-wrap gap-1.5 text-label">
                    {views.data.committee.map((c, i) => (
                      <span key={i} className="text-gray-500">
                        {humanizePersonaId(c.persona_id)}:{" "}
                        <span className="text-gray-300">
                          {c.analysis?.stance ?? "—"}
                        </span>
                      </span>
                    ))}
                  </div>
                  <PersonaOpinionGrid
                    committee={views.data.committee}
                    committeeRound1={views.data.committee_round1 ?? null}
                    synthesisAnalysis={views.data.ai_full ?? undefined}
                    showSynthesisFirst
                    compact
                  />
                </div>
              )}
          </td>
        </tr>
      )}
    </>
  );
}

export function ScreenersView() {
  const { screenId } = useParams();
  const active = getScreenerById(screenId);
  const [viewsForTicker, setViewsForTicker] = useState<string | null>(null);

  if (!active) {
    return <Navigate to={`/screeners/${DEFAULT_SCREENER_ID}`} replace />;
  }

  return (
    <div className="flex flex-col min-h-screen">
      <AppNav active="screeners" />

      <div className="p-6 max-w-7xl mx-auto w-full flex flex-col gap-6 grow">
        <div>
          <h1 className="text-2xl font-bold text-white">Screeners</h1>
          <p className="text-gray-500 text-sm mt-1">
            Fundamental screeners powered by yfinance. Each model applies hard
            filters and a weighted scoring framework — results link directly to
            research for AI committee analysis.
          </p>
        </div>

        <div className="flex flex-wrap gap-2 border-b border-border pb-3">
          {SCREENER_VIEWS.map((v) => (
            <Link
              key={v.id}
              to={`/screeners/${v.id}`}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                v.id === active.id
                  ? "bg-blue-500/20 text-blue-400 font-medium"
                  : "text-gray-500 hover:text-gray-300 hover:bg-surface-card"
              }`}
            >
              {v.label}
            </Link>
          ))}
        </div>

        {active.usesApi && active.screenId && (
          <ScreenResults
            screen={active.screenId}
            title={active.resultsTitle ?? active.label}
            blurb={active.resultsBlurb ?? active.description}
            info={active.infoTerm}
            scoreMax={active.scoreMax ?? 100}
          />
        )}

        <div>
          <h2 className="font-display text-title-xs text-bone">{active.label}</h2>
          <p className="mt-2xs max-w-measure text-body-sm text-on-ink-soft">
            {active.description}
          </p>
        </div>

        {/* The recipe, folded away. It was above the results and three
          * screenfuls long, so the answer was always below the fold. */}
        <details className="border border-ink-line bg-ink-raised">
          <summary className="cursor-pointer list-none px-md py-sm font-display text-label uppercase tracking-label text-on-ink-soft transition-colors hover:text-bone [&::-webkit-details-marker]:hidden">
            What this screen tests ▾
          </summary>
          <div className="border-t border-ink-line px-md py-sm">
            {active.criteriaSections && active.criteriaSections.length > 0 ? (
              <div className="space-y-5">
                {active.criteriaSections.map((sec) => (
                  <div key={sec.title}>
                    <p className="mb-2 font-display text-label uppercase tracking-label text-on-ink-faint">
                      {sec.title}
                    </p>
                    <ul className="list-inside list-disc space-y-1 text-body-xs text-on-ink-soft">
                      {sec.items.map((c, i) => (
                        <li key={`${sec.title}-${i}`}>{c}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            ) : (
              <ul className="list-inside list-disc space-y-1 text-body-xs text-on-ink-soft">
                {active.criteria.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            )}
          </div>
        </details>

        {/* Run it somewhere else. Optional, and precise about what "another
          * market" means here, because the two kinds behave nothing alike:
          * the three S&P bands are whole indices, several hundred names and
          * ten-plus minutes each, while Japan, Korea, Europe and the rest are
          * curated watchlists of roughly twenty large caps that finish in
          * about a minute. Offering them as one undifferentiated list invites
          * someone to start a quarter-hour run expecting the short one. */}
        {active.usesApi && (
          <details className="border border-ink-line bg-ink-raised">
            <summary className="cursor-pointer list-none px-md py-sm font-display text-label uppercase tracking-label text-on-ink-soft transition-colors hover:text-bone [&::-webkit-details-marker]:hidden">
              Run it on another market — Japan, Korea, Europe — or a full index ▾
            </summary>
            <div className="border-t border-ink-line p-md">
              <p className="mb-md max-w-measure text-body-xs text-on-ink-faint">
                These run live, one company at a time. The market watchlists —
                Japan, Korea, Europe, India, Brazil and a dozen more — are
                around twenty large caps each and take about a minute. A full
                S&P band is several hundred names and takes ten minutes or
                more, so cap it if you only want a look.
              </p>
              {active.id === "yartseva" ? (
                <YartsevaPanel />
              ) : (
                <AcquisitionCompounderPanel />
              )}
            </div>
          </details>
        )}

        {!active.usesApi && (
          <div className="bg-surface-card rounded-xl border border-border/60 overflow-hidden">
            <div className="px-5 py-3 border-b border-border/60 flex items-center justify-between">
              <span className="text-sm font-medium text-gray-300">Plays</span>
              <span className="text-xs text-gray-600">
                {active.plays.length} row(s)
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse min-w-[720px]">
                <thead>
                  <tr className="text-gray-500 text-xs uppercase tracking-wider border-b border-border">
                    <th className="py-3 px-5 font-medium">Ticker</th>
                    <th className="py-3 pr-4 font-medium">Setup</th>
                    <th className="py-3 pr-4 font-medium">Entry</th>
                    <th className="py-3 pr-4 font-medium">Stop</th>
                    <th className="py-3 pr-4 font-medium">Target</th>
                    <th className="py-3 pr-4 font-medium">Sizing</th>
                    <th className="py-3 pr-4 font-medium">Notes</th>
                    <th className="py-3 pr-2 font-medium text-right w-[7rem]">
                      AI
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {active.plays.length === 0 ? (
                    <tr>
                      <td
                        colSpan={8}
                        className="py-10 text-center text-gray-500 text-sm"
                      >
                        No plays yet for this view. Add rows in{" "}
                        <code className="text-gray-400">
                          config/screeners.ts
                        </code>{" "}
                        or connect a screener API.
                      </td>
                    </tr>
                  ) : (
                    active.plays.map((p, i) => (
                      <PlayRow
                        key={`${p.ticker}-${i}`}
                        p={p}
                        expanded={viewsForTicker === p.ticker}
                        onToggleViews={() =>
                          setViewsForTicker((cur) =>
                            cur === p.ticker ? null : p.ticker,
                          )
                        }
                      />
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
