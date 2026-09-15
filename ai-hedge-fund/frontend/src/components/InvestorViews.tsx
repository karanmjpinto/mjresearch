import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type ResearchCheckResponse } from "@/lib/api";
import {
  PersonaOpinionGrid,
  PersonaCard,
  humanizePersonaId,
} from "./PersonaOpinionCards";
import { RunTimeline, recordRuntime, type RunStage } from "./RunTimeline";
/* Signal intelligence reads the model's output against the analyst and
 * sentiment feeds, so it belongs beside the views rather than on the data
 * screen it used to sit on. It still lives in ResearchReport.tsx, which is now
 * the wrong home for it — a follow-up should move it to its own file with the
 * helpers it depends on. */
import { SignalIntelligence } from "./ResearchReport";

/**
 * What named investors make of this company.
 *
 * This used to sit behind a "Run AI thesis" button on the data screen, which
 * made the most opinionated thing in the app the one piece you had to know to
 * ask for — and put it a tab away from the analysis that weighs it. It now
 * runs as soon as a symbol is open, because opening a company *is* the request.
 *
 * The button that remains is a re-run, not a gate. Two reasons it still exists:
 * a local model's answer is not deterministic, so seeing it twice is a real
 * check; and switching lens (committee, one investor, generic) is a different
 * question that deserves a fresh pass rather than a cached one.
 */

type Mode = "committee" | "persona" | "default";

const MODES: readonly [Mode, string, string][] = [
  [
    "committee",
    "Committee",
    "Each style on the same data, then a portfolio-manager synthesis.",
  ],
  ["persona", "One investor", "A single named style, argued at length."],
  ["default", "Generic analyst", "No house style — a plain read."],
];

export function InvestorViews({ ticker }: { ticker: string }) {
  const [mode, setMode] = useState<Mode>("committee");
  const [personaId, setPersonaId] = useState("warren_buffett");
  const [nonce, setNonce] = useState(0);
  const [completedIn, setCompletedIn] = useState<number | null>(null);
  const startedAt = useRef<number | null>(null);

  const personas = useQuery({
    queryKey: ["personas"],
    queryFn: api.getPersonas,
    staleTime: Infinity,
  });

  const run = useQuery({
    // `nonce` is in the key so a re-run is a new query rather than a refetch of
    // a cached one — the whole point of pressing it is to not get the old answer.
    queryKey: [
      "investor-views",
      ticker,
      mode,
      mode === "persona" ? personaId : null,
      nonce,
    ],
    queryFn: () =>
      api.checkTicker(ticker, {
        includeAi: true,
        committee: mode === "committee",
        persona: mode === "persona" ? personaId : null,
      }),
    enabled: Boolean(ticker),
    // A run costs tens of seconds of local compute, so it is never retried
    // automatically and never silently refetched behind the reader.
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    gcTime: 30 * 60_000,
  });

  // Timing is measured around the fetch rather than taken from the response,
  // because the endpoint does not report its own duration.
  useEffect(() => {
    if (run.isFetching) {
      startedAt.current = Date.now();
      setCompletedIn(null);
    } else if (startedAt.current != null) {
      const secs = (Date.now() - startedAt.current) / 1000;
      startedAt.current = null;
      setCompletedIn(secs);
      if (run.isSuccess) recordRuntime(`views:${mode}`, secs);
    }
  }, [run.isFetching, run.isSuccess, mode]);

  const d: ResearchCheckResponse | undefined = run.data;
  const ai = d?.ai_full;

  // Only fetched once there is a model view to read them against — on their
  // own these are two more feeds, not a signal.
  const hasView = Boolean(ai) || (d?.committee?.length ?? 0) > 0;

  const analystSig = useQuery({
    queryKey: ["analyst-sig", ticker],
    queryFn: () => api.getAnalyst(ticker),
    enabled: Boolean(ticker) && hasView,
    retry: false,
    staleTime: 5 * 60_000,
  });

  const sentimentSig = useQuery({
    queryKey: ["sentiment-sig", ticker],
    queryFn: () => api.getSentiment(ticker),
    enabled: Boolean(ticker) && hasView,
    retry: false,
    staleTime: 5 * 60_000,
  });

  const committeeIds = personas.data?.default_committee ?? [];

  const stages: RunStage[] =
    mode === "committee"
      ? [
          {
            label: "Pull the snapshot",
            detail: "prices, fundamentals, technicals",
          },
          ...committeeIds.map((id) => ({ label: humanizePersonaId(id) })),
          { label: "Portfolio-manager synthesis" },
          { label: "Check the prose against the numbers" },
        ]
      : [
          {
            label: "Pull the snapshot",
            detail: "prices, fundamentals, technicals",
          },
          {
            label:
              mode === "persona"
                ? humanizePersonaId(personaId)
                : "Generic analyst",
          },
          { label: "Check the prose against the numbers" },
        ];

  const aiError = d?.ai_error
    ? (d.ai_error.message ?? d.ai_error.error)
    : run.error instanceof Error
      ? run.error.message
      : null;

  return (
    <div className="flex flex-col gap-md">
      <div className="flex flex-wrap items-start justify-between gap-md">
        <div>
          <h2 className="font-display text-label uppercase tracking-label text-on-ink-faint">
            Investor lens
          </h2>
          <div className="mt-xs flex flex-wrap gap-xs">
            {MODES.map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setMode(id)}
                aria-current={mode === id ? "true" : undefined}
                className={`border px-sm py-1.5 font-display text-label uppercase tracking-label transition-colors focus-visible:outline-none ${
                  mode === id
                    ? "border-cadmium text-cadmium"
                    : "border-ink-line text-on-ink-soft hover:border-cobalt hover:text-bone focus-visible:border-cobalt"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="mt-2xs max-w-[60ch] text-body-xs text-on-ink-faint">
            {MODES.find(([id]) => id === mode)?.[2]}
          </p>

          {mode === "persona" && (
            <label className="mt-sm flex flex-col gap-2xs">
              <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
                Whose lens
              </span>
              <select
                value={personaId}
                onChange={(e) => setPersonaId(e.target.value)}
                className="max-w-[280px] border border-ink-line bg-ink px-sm py-1.5 font-display text-label text-bone outline-none transition-colors focus:border-cobalt"
              >
                {(personas.data?.personas ?? [])
                  .filter((p) => p.id !== "default")
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {humanizePersonaId(p.id)}
                    </option>
                  ))}
              </select>
            </label>
          )}
        </div>

        <button
          type="button"
          onClick={() => setNonce((n) => n + 1)}
          disabled={run.isFetching}
          className="shrink-0 border border-ink-line px-sm py-1.5 font-display text-label uppercase tracking-label text-on-ink-soft transition-colors hover:border-cadmium hover:text-cadmium focus-visible:border-cadmium focus-visible:outline-none disabled:opacity-50"
        >
          {run.isFetching ? "Running…" : "Run again"}
        </button>
      </div>

      <RunTimeline
        running={run.isFetching}
        stages={stages}
        kind={`views:${mode}`}
        completedIn={completedIn}
        error={run.isFetching ? null : aiError}
      />

      {/* An empty state that is not a nudge to press something. If there is
       * nothing here and nothing running, the reason is a failure, and the
       * timeline above is already carrying it. */}
      {!run.isFetching &&
        !aiError &&
        !ai &&
        (d?.committee?.length ?? 0) === 0 && (
          <p className="max-w-[72ch] text-body-sm text-on-ink-soft">
            The model returned no view for {ticker}. That is usually a model
            that is not running rather than a company it had nothing to say
            about.
          </p>
        )}

      {!aiError &&
        mode === "committee" &&
        d?.committee &&
        d.committee.length > 0 && (
          <PersonaOpinionGrid
            committee={d.committee}
            committeeRound1={d.committee_round1 ?? null}
            synthesisAnalysis={ai ?? undefined}
            showSynthesisFirst
          />
        )}

      {!aiError && hasView && ai && (
        <SignalIntelligence
          ai={ai}
          committee={d?.committee ?? null}
          refinement={d?.refinement ?? null}
          dissent={d?.dissent ?? null}
          analyst={analystSig.data ?? null}
          sentiment={sentimentSig.data ?? null}
          newsSentimentMean={
            d?.news_sentiment?.enabled
              ? d.news_sentiment.aggregate.mean_signed
              : null
          }
        />
      )}

      {!aiError && mode === "persona" && ai && (
        <div className="max-w-3xl">
          <PersonaCard
            entry={{ persona_id: d?.persona_id ?? personaId, analysis: ai }}
            accentIndex={0}
          />
        </div>
      )}

      {!aiError && mode === "default" && ai && (
        <div className="max-w-3xl border border-ink-line bg-ink-raised p-md shadow-elev-1">
          <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
            Generic analyst
          </p>
          <p className="mt-xs whitespace-pre-wrap text-body-sm leading-relaxed text-on-ink">
            {ai.investment_thesis}
          </p>
          <div className="mt-sm grid gap-sm border-t border-ink-line pt-sm md:grid-cols-2">
            <p className="text-body-xs text-on-ink-soft">
              <span className="text-verdigris">Bull:</span> {ai.bull_case}
            </p>
            <p className="text-body-xs text-on-ink-soft">
              <span className="text-oxide">Bear:</span> {ai.bear_case}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
