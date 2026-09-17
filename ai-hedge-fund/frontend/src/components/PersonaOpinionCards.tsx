import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type AiAnalysisBlock, type CommitteeEntry } from "@/lib/api";
import { Popover } from "./Popover";

/** Map persona_id to short display label */
export function humanizePersonaId(id: string): string {
  const map: Record<string, string> = {
    default: "Analyst",
    warren_buffett: "Warren Buffett",
    ben_graham: "Ben Graham",
    bill_ackman: "Bill Ackman",
    cathie_wood: "Cathie Wood",
    anthony_bolton: "Anthony Bolton",
    norbert_lou: "Norbert Lou",
    li_lu: "Li Lu",
    charlie_munger: "Charlie Munger",
    michael_burry: "Michael Burry",
    mohnish_pabrai: "Mohnish Pabrai",
    peter_lynch: "Peter Lynch",
    phil_fisher: "Phil Fisher",
    rakesh_jhunjhunwala: "Rakesh Jhunjhunwala",
    stanley_druckenmiller: "Stanley Druckenmiller",
    aswath_damodaran: "Aswath Damodaran",
  };
  return (
    map[id] ?? id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

/**
 * Colour says what the analyst concluded, not who they are.
 *
 * These cards used to be tinted by position in the list — violet, cyan, rose,
 * amber, emerald, blue gradients — which spent six hues on the one thing that
 * carries no meaning. Nothing follows from Cathie Wood being the fourth card,
 * and against a palette of oxide, cadmium, cobalt and verdigris the rainbow
 * read as a different product bolted on.
 *
 * So the accent is the stance. Four verdicts, four of the app's own colours,
 * and a card that is visually identical to its neighbour until they disagree —
 * at which point the disagreement is the first thing you see, which is the
 * whole reason for running a committee.
 */
function stanceStyles(stance: string | undefined): string {
  const s = (stance ?? "").toUpperCase();
  if (s === "BUY") return "border-verdigris bg-verdigris/12 text-verdigris";
  if (s === "SELL") return "border-oxide bg-oxide/12 text-oxide";
  if (s === "WATCH") return "border-cobalt bg-cobalt/12 text-cobalt";
  return "border-ink-line bg-ink text-on-ink-soft";
}

/** The rail down the card's edge, same reading as the badge. */
function stanceRail(stance: string | undefined): string {
  const s = (stance ?? "").toUpperCase();
  if (s === "BUY") return "border-l-verdigris";
  if (s === "SELL") return "border-l-oxide";
  if (s === "WATCH") return "border-l-cobalt";
  return "border-l-ink-line";
}

/**
 * Who this is, how they think, and what they actually check.
 *
 * The third part is the reason this panel exists. A verdict from "Anthony
 * Bolton" means nothing unless you can see the standard being applied — and
 * once you can, a SELL on a great company stops looking like an error and
 * starts looking like the lens working. So the concrete tests are listed, not
 * summarised.
 *
 * All of it comes from the persona endpoint, which serves the same profile
 * that builds the prompt. A copy kept in the frontend drifted from the
 * instruction the model was given, which made this panel confidently wrong
 * about the very thing it exists to explain.
 */
function PersonaNote({ personaId, name }: { personaId: string; name: string }) {
  const personas = useQuery({
    queryKey: ["personas"],
    queryFn: api.getPersonas,
    staleTime: Infinity,
  });
  const p = personas.data?.personas.find((x) => x.id === personaId);
  if (!p?.who) return null;
  return (
    <Popover label={`Who is ${name}, and how do they judge?`} width={26}>
      <span className="block font-display text-label uppercase tracking-label text-cadmium">
        {name}
      </span>
      {p.essence && (
        <span className="block text-body-xs italic leading-relaxed text-on-ink">
          {p.essence}
        </span>
      )}
      <span className="block text-body-xs leading-relaxed text-on-ink-soft">{p.who}</span>
      {p.style && (
        <span className="block border-t border-ink-line pt-xs text-body-xs leading-relaxed text-on-ink-soft">
          {p.style}
        </span>
      )}
      {p.tests && p.tests.length > 0 && (
        <span className="block border-t border-ink-line pt-xs">
          <span className="mb-2xs block font-display text-label uppercase tracking-label text-on-ink-faint">
            What they check
          </span>
          <ul className="flex flex-col gap-2xs">
            {p.tests.map((t) => (
              <li
                key={t}
                className="flex gap-xs text-body-xs leading-relaxed text-on-ink-soft"
              >
                <span aria-hidden="true" className="text-cobalt">
                  ·
                </span>
                <span>{t}</span>
              </li>
            ))}
          </ul>
        </span>
      )}
    </Popover>
  );
}

function MiniConviction({ score }: { score: number | null | undefined }) {
  if (score == null)
    return <span className="text-gray-600 text-xs font-mono">—</span>;
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 min-w-[48px] flex-1 overflow-hidden bg-ink-line">
        <div
          className="h-full bg-cobalt transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 font-display text-label tabular text-bone">
        {Math.round(pct)}
      </span>
    </div>
  );
}

export function PersonaCard({
  entry,
  compact = false,
  priorAnalysis = null,
}: {
  entry: CommitteeEntry;
  compact?: boolean;
  /** This analyst's round-1 view, when a rebuttal round changed their mind. */
  priorAnalysis?: AiAnalysisBlock | null;
}) {
  const [open, setOpen] = useState(false);
  const [showPrior, setShowPrior] = useState(false);
  const name = humanizePersonaId(entry.persona_id);
  const rail = stanceRail(entry.analysis?.stance);

  if (entry.error) {
    return (
      <div className="border border-dashed border-oxide bg-ink-raised p-md">
        <p className="text-sm font-semibold text-gray-300">{name}</p>
        <p className="mt-2xs text-body-xs text-oxide">
          {(entry.error as { message?: string }).message ??
            String((entry.error as { error?: string }).error ?? "Error")}
        </p>
      </div>
    );
  }

  const a = entry.analysis as AiAnalysisBlock | undefined;
  if (!a) {
    return (
      <div className="border border-ink-line bg-ink-raised p-md">
        <p className="text-sm font-semibold text-gray-300">{name}</p>
        <p className="text-xs text-gray-500 mt-1">No analysis returned</p>
      </div>
    );
  }

  return (
    <div
      className={`flex min-h-[8rem] flex-col gap-xs border border-l-2 border-ink-line bg-ink-raised p-md shadow-elev-1 ${rail}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="flex items-center gap-xs font-display text-mark text-bone">
            {name}
            <PersonaNote personaId={entry.persona_id} name={name} />
          </p>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span
              className={`text-label uppercase tracking-wider px-2 py-0.5 rounded border font-semibold ${stanceStyles(a.stance)}`}
            >
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
                  className="text-label uppercase tracking-wider px-2 py-0.5 rounded border border-cadmium bg-cadmium/12 text-cadmium transition-colors hover:bg-cadmium/20"
                >
                  revised from {entry.stance_before ?? "—"}{" "}
                  <span className="tabular">
                    {entry.conviction_before ?? "—"}
                  </span>
                  {showPrior ? " ▴" : " ▾"}
                </button>
              ) : (
                <span
                  className="text-label uppercase tracking-wider px-2 py-0.5 rounded border border-cadmium bg-cadmium/12 text-cadmium"
                  title={`Revised after the rebuttal round — opened at ${entry.stance_before ?? "—"} ${entry.conviction_before ?? "—"}`}
                >
                  revised from {entry.stance_before ?? "—"}{" "}
                  <span className="tabular">
                    {entry.conviction_before ?? "—"}
                  </span>
                </span>
              ))}
            {entry.round === 2 && !entry.revised && (
              <span
                className="text-label uppercase tracking-wider px-2 py-0.5 rounded border border-verdigris bg-verdigris/12 text-verdigris"
                title="Saw the other analysts' conclusions and did not move"
              >
                held
              </span>
            )}
            {!compact && (
              <span className="text-label text-gray-500">
                data conf. {a.confidence_in_data ?? "—"}/5
              </span>
            )}
          </div>
        </div>
        <div className="shrink-0 w-24">
          <MiniConviction score={a.conviction_score} />
        </div>
      </div>
      {showPrior && priorAnalysis && (
        <div className="rounded-lg border border-cadmium/40 bg-cadmium/8 p-3 space-y-1">
          <p className="text-label uppercase tracking-wider text-cadmium">
            Opening view — before seeing the others
          </p>
          <p className="text-xs text-gray-300 leading-relaxed">
            {priorAnalysis.investment_thesis}
          </p>
          {priorAnalysis.bear_case && (
            <p className="text-label text-gray-500">
              <span className="text-oxide">Bear:</span>{" "}
              {priorAnalysis.bear_case}
            </p>
          )}
        </div>
      )}
      <p
        className={`text-xs text-gray-300 leading-relaxed ${compact && !open ? "line-clamp-2" : ""}`}
      >
        {a.investment_thesis}
      </p>
      {(compact ? open : true) && a.bull_case && (
        <div className="text-label text-gray-500 border-t border-ink-line pt-xs space-y-1">
          <p>
            <span className="text-verdigris">Bull:</span> {a.bull_case}
          </p>
          {!compact && a.bear_case && (
            <p>
              <span className="text-oxide">Bear:</span> {a.bear_case}
            </p>
          )}
        </div>
      )}
      {compact && (a.investment_thesis?.length ?? 0) > 120 && (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="self-start font-display text-label uppercase tracking-label text-cobalt transition-colors hover:text-cadmium"
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
    <div className="border border-l-2 border-ink-line border-l-cadmium bg-ink-raised p-md shadow-elev-2">
      <div className="flex items-center gap-2 mb-3">
        <span className="font-display text-label uppercase tracking-marker text-cadmium">
          Committee synthesis
        </span>
        <span
          className={`text-label px-2 py-0.5 rounded border font-semibold ${stanceStyles(analysis.stance)}`}
        >
          {analysis.stance}
        </span>
        <MiniConviction score={analysis.conviction_score} />
      </div>
      <p className="text-sm text-gray-100 leading-relaxed whitespace-pre-wrap">
        {analysis.investment_thesis}
      </p>
      <div className="grid md:grid-cols-2 gap-3 mt-4 text-xs">
        <div className="bg-black/20 rounded-lg p-3 border border-white/5">
          <p className="mb-2xs font-display text-label uppercase tracking-label text-verdigris">
            Bull
          </p>
          <p className="text-gray-300">{analysis.bull_case}</p>
        </div>
        <div className="bg-black/20 rounded-lg p-3 border border-white/5">
          <p className="mb-2xs font-display text-label uppercase tracking-label text-oxide">
            Bear
          </p>
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
      {showSynthesisFirst && synthesisAnalysis && (
        <SynthesisCard analysis={synthesisAnalysis} />
      )}
      <div className="grid sm:grid-cols-2 xl:grid-cols-2 gap-3">
        {committee.map((c, i) => (
          <PersonaCard
            key={`${c.persona_id}-${i}`}
            entry={c}
            compact={compact}
            priorAnalysis={priorByPersona.get(c.persona_id) ?? null}
          />
        ))}
      </div>
    </div>
  );
}
