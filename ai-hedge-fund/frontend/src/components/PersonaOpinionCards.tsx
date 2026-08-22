import { useState } from "react";
import type { AiAnalysisBlock, CommitteeEntry } from "@/lib/api";

/** Map persona_id to short display label */
export function humanizePersonaId(id: string): string {
  const map: Record<string, string> = {
    default: "Analyst",
    warren_buffett: "Warren Buffett",
    ben_graham: "Ben Graham",
    bill_ackman: "Bill Ackman",
    cathie_wood: "Cathie Wood",
    charlie_munger: "Charlie Munger",
    michael_burry: "Michael Burry",
    mohnish_pabrai: "Mohnish Pabrai",
    peter_lynch: "Peter Lynch",
    phil_fisher: "Phil Fisher",
    rakesh_jhunjhunwala: "Rakesh Jhunjhunwala",
    stanley_druckenmiller: "Stanley Druckenmiller",
    aswath_damodaran: "Aswath Damodaran",
  };
  return map[id] ?? id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function stanceStyles(stance: string | undefined): string {
  const s = (stance ?? "").toUpperCase();
  if (s === "BUY") return "bg-emerald-500/20 text-emerald-400 border-emerald-500/40";
  if (s === "SELL") return "bg-red-500/20 text-red-400 border-red-500/40";
  if (s === "WATCH") return "bg-amber-500/20 text-amber-400 border-amber-500/40";
  return "bg-slate-500/20 text-slate-300 border-slate-500/40";
}

const ACCENT = [
  "from-violet-500/20 to-transparent border-violet-500/30",
  "from-cyan-500/20 to-transparent border-cyan-500/30",
  "from-amber-500/20 to-transparent border-amber-500/30",
  "from-rose-500/20 to-transparent border-rose-500/30",
  "from-emerald-500/20 to-transparent border-emerald-500/30",
  "from-blue-500/20 to-transparent border-blue-500/30",
];

function MiniConviction({ score }: { score: number | null | undefined }) {
  if (score == null) return <span className="text-gray-600 text-xs font-mono">—</span>;
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 rounded-full bg-surface-elevated overflow-hidden min-w-[48px]">
        <div
          className="h-full rounded-full bg-gradient-to-r from-blue-600 to-emerald-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-mono text-white tabular-nums w-8">{Math.round(pct)}</span>
    </div>
  );
}

export function PersonaCard({
  entry,
  accentIndex = 0,
  compact = false,
  priorAnalysis = null,
}: {
  entry: CommitteeEntry;
  accentIndex?: number;
  compact?: boolean;
  /** This analyst's round-1 view, when a rebuttal round changed their mind. */
  priorAnalysis?: AiAnalysisBlock | null;
}) {
  const [open, setOpen] = useState(false);
  const [showPrior, setShowPrior] = useState(false);
  const name = humanizePersonaId(entry.persona_id);
  const accent = ACCENT[accentIndex % ACCENT.length]!;

  if (entry.error) {
    return (
      <div
        className={`rounded-xl border bg-gradient-to-br ${accent} p-4 border-dashed`}
      >
        <p className="text-sm font-semibold text-gray-300">{name}</p>
        <p className="text-xs text-red-400 mt-1">
          {(entry.error as { message?: string }).message ?? String((entry.error as { error?: string }).error ?? "Error")}
        </p>
      </div>
    );
  }

  const a = entry.analysis as AiAnalysisBlock | undefined;
  if (!a) {
    return (
      <div className={`rounded-xl border bg-gradient-to-br ${accent} p-4`}>
        <p className="text-sm font-semibold text-gray-300">{name}</p>
        <p className="text-xs text-gray-500 mt-1">No analysis returned</p>
      </div>
    );
  }

  return (
    <div
      className={`rounded-xl border bg-gradient-to-br ${accent} p-4 flex flex-col gap-2 min-h-[8rem]`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-white">{name}</p>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className={`text-label uppercase tracking-wider px-2 py-0.5 rounded border font-semibold ${stanceStyles(a.stance)}`}>
              {a.stance ?? "—"}
            </span>
            {/* An opinion formed after seeing the others is weaker evidence than
                one formed independently, and one held under disagreement is
                stronger. Neither is visible from the final number alone. */}
            {entry.round === 2 &&
              entry.revised &&
              (priorAnalysis ? (
                <button
                  type="button"
                  onClick={() => setShowPrior(!showPrior)}
                  aria-expanded={showPrior}
                  title="Read the view this analyst held before seeing the others"
                  className="text-label uppercase tracking-wider px-2 py-0.5 rounded border border-amber-500/40 bg-amber-500/10 text-amber-300 transition-colors hover:bg-amber-500/20"
                >
                  revised from {entry.stance_before ?? "—"}{" "}
                  <span className="tabular">{entry.conviction_before ?? "—"}</span>
                  {showPrior ? " ▴" : " ▾"}
                </button>
              ) : (
                <span
                  className="text-label uppercase tracking-wider px-2 py-0.5 rounded border border-amber-500/40 bg-amber-500/10 text-amber-300"
                  title={`Revised after the rebuttal round — opened at ${entry.stance_before ?? "—"} ${entry.conviction_before ?? "—"}`}
                >
                  revised from {entry.stance_before ?? "—"}{" "}
                  <span className="tabular">{entry.conviction_before ?? "—"}</span>
                </span>
              ))}
            {entry.round === 2 && !entry.revised && (
              <span
                className="text-label uppercase tracking-wider px-2 py-0.5 rounded border border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                title="Saw the other analysts' conclusions and did not move"
              >
                held
              </span>
            )}
            {!compact && (
              <span className="text-label text-gray-500">data conf. {a.confidence_in_data ?? "—"}/5</span>
            )}
          </div>
        </div>
        <div className="shrink-0 w-24">
          <MiniConviction score={a.conviction_score} />
        </div>
      </div>
      {showPrior && priorAnalysis && (
        <div className="rounded-lg border border-amber-500/25 bg-amber-500/5 p-3 space-y-1">
          <p className="text-label uppercase tracking-wider text-amber-300/80">
            Opening view — before seeing the others
          </p>
          <p className="text-xs text-gray-300 leading-relaxed">
            {priorAnalysis.investment_thesis}
          </p>
          {priorAnalysis.bear_case && (
            <p className="text-label text-gray-500">
              <span className="text-red-400/90">Bear:</span> {priorAnalysis.bear_case}
            </p>
          )}
        </div>
      )}
      <p className={`text-xs text-gray-300 leading-relaxed ${compact && !open ? "line-clamp-2" : ""}`}>
        {a.investment_thesis}
      </p>
      {(compact ? open : true) && a.bull_case && (
        <div className="text-label text-gray-500 border-t border-white/5 pt-2 space-y-1">
          <p>
            <span className="text-emerald-500/90">Bull:</span> {a.bull_case}
          </p>
          {!compact && a.bear_case && (
            <p>
              <span className="text-red-400/90">Bear:</span> {a.bear_case}
            </p>
          )}
        </div>
      )}
      {compact && (a.investment_thesis?.length ?? 0) > 120 && (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="text-label text-blue-400 hover:text-blue-300 self-start"
        >
          {open ? "Show less" : "Read full view"}
        </button>
      )}
    </div>
  );
}

/** Portfolio-manager synthesis (committee output) */
export function SynthesisCard({ analysis }: { analysis: AiAnalysisBlock }) {
  return (
    <div className="rounded-xl border border-blue-500/40 bg-gradient-to-br from-blue-500/15 to-slate-900/80 p-5 shadow-lg shadow-blue-900/20">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xs font-bold uppercase tracking-widest text-blue-400">Committee synthesis</span>
        <span className={`text-label px-2 py-0.5 rounded border font-semibold ${stanceStyles(analysis.stance)}`}>
          {analysis.stance}
        </span>
        <MiniConviction score={analysis.conviction_score} />
      </div>
      <p className="text-sm text-gray-100 leading-relaxed whitespace-pre-wrap">{analysis.investment_thesis}</p>
      <div className="grid md:grid-cols-2 gap-3 mt-4 text-xs">
        <div className="bg-black/20 rounded-lg p-3 border border-white/5">
          <p className="text-emerald-400/90 font-medium mb-1">Bull</p>
          <p className="text-gray-300">{analysis.bull_case}</p>
        </div>
        <div className="bg-black/20 rounded-lg p-3 border border-white/5">
          <p className="text-red-400/90 font-medium mb-1">Bear</p>
          <p className="text-gray-300">{analysis.bear_case}</p>
        </div>
      </div>
      {analysis.key_risks?.length > 0 && (
        <ul className="mt-3 text-xs text-gray-400 list-disc list-inside space-y-0.5">
          {analysis.key_risks.slice(0, 8).map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function PersonaOpinionGrid({
  committee,
  committeeRound1 = null,
  synthesisAnalysis,
  showSynthesisFirst = true,
  compact = false,
}: {
  committee: CommitteeEntry[];
  /** Round-1 views, when a rebuttal round ran. Matched to cards by persona. */
  committeeRound1?: CommitteeEntry[] | null;
  synthesisAnalysis?: AiAnalysisBlock | null;
  showSynthesisFirst?: boolean;
  compact?: boolean;
}) {
  const priorByPersona = new Map<string, AiAnalysisBlock>();
  for (const c of committeeRound1 ?? []) {
    if (c.analysis) priorByPersona.set(c.persona_id, c.analysis);
  }

  return (
    <div className="flex flex-col gap-4">
      {showSynthesisFirst && synthesisAnalysis && <SynthesisCard analysis={synthesisAnalysis} />}
      <div className="grid sm:grid-cols-2 xl:grid-cols-2 gap-3">
        {committee.map((c, i) => (
          <PersonaCard
            key={`${c.persona_id}-${i}`}
            entry={c}
            accentIndex={i}
            compact={compact}
            priorAnalysis={priorByPersona.get(c.persona_id) ?? null}
          />
        ))}
      </div>
    </div>
  );
}
