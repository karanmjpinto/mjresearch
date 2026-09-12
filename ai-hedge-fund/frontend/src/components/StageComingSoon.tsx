import { useParams } from "react-router-dom";
import { AppNav } from "@/components/AppNav";
import { CompsField } from "@/components/CompsField";
import { ConvictionChain } from "@/components/ConvictionChain";
import { IntrinsicValue } from "@/components/IntrinsicValue";
import { STAGES, type StageKey } from "@/lib/flow";

/**
 * A stage that is on the rail but not yet built.
 *
 * The alternative was to leave these two off the rail until their phase lands,
 * which would misrepresent the flow as four stages rather than six, and make
 * the later arrival of valuation feel like a new feature rather than the piece
 * the whole path was pointing at. So the stage exists, says what it will
 * answer, and says which phase brings it — which is more useful than a spinner
 * over an empty panel.
 */

const PLANNED: Record<string, { phase: string; bullets: string[] }> = {
  lens: {
    phase: "Phase 3",
    bullets: [
      "Every note in your vault that touches this name, labelled by how it connects: a company page, a sector or theme note, or a framework that applies.",
      "Coverage — how much of your own thinking this name sits inside. Thin coverage is a finding, not a failure.",
      "Your frameworks applied as lenses: 7 Powers, Technical Moat Assessment, Valuing a Compounder, Equity Risk Premiums.",
      "No page yet? Draft a Value One Pager in your own template, pre-linked to the notes it matched.",
    ],
  },
  value: {
    phase: "Phase 2",
    bullets: [
      "Four drivers from the story — growth, target margin, reinvestment, cost of capital — plus a probability of failure.",
      "Cost of capital built up from the risk-free rate, beta, the equity risk premium and a revenue-weighted country premium.",
      "10,000 simulated draws, giving a distribution of value per share with today's price marked on it.",
      "Conviction as Damodaran defines it: your fair price is right, the market corrects, and it corrects inside your horizon — multiplied, so one weak leg caps the result.",
    ],
  },
};

export function StageComingSoon({ stage }: { stage: Extract<StageKey, "lens" | "value"> }) {
  const { ticker } = useParams();
  const spec = STAGES.find((s) => s.key === stage);
  const planned = PLANNED[stage];

  return (
    <div className="flex min-h-dvh flex-col bg-ink">
      <AppNav active={stage === "lens" ? "research" : "plan"} />

      <main className="mx-auto w-full max-w-4xl px-lg py-2xl">
        <p className="font-display text-label uppercase tracking-marker text-on-ink-faint">
          Stage {spec?.num} {ticker ? `· ${ticker.toUpperCase()}` : ""}
        </p>
        <h1 className="mt-xs font-display text-display-sm text-bone">{spec?.label}</h1>
        <p className="mt-sm max-w-[60ch] text-body-lg text-on-ink-soft">{spec?.question}</p>

        {/* The first piece of this stage that is real. A comparable-company
            range is a valuation method, so it lands here rather than waiting
            for the rest of the engine. */}
        {stage === "value" && ticker && (
          <div className="mt-xl flex flex-col gap-2xl border-t border-ink-line pt-lg">
            <CompsField ticker={ticker.toUpperCase()} />
            <IntrinsicValue ticker={ticker.toUpperCase()} />
            <ConvictionChain ticker={ticker.toUpperCase()} />
          </div>
        )}

        <div className="mt-xl border-l-2 border-cadmium pl-md">
          <p className="font-display text-label uppercase tracking-label text-cadmium">
            {planned.phase} — still to come
          </p>
          <ul className="mt-sm flex flex-col gap-sm">
            {planned.bullets.map((b) => (
              <li key={b} className="max-w-[68ch] text-body-sm text-on-ink-soft">
                {b}
              </li>
            ))}
          </ul>
        </div>

        <p className="mt-xl max-w-[68ch] text-body-sm text-on-ink-faint">
          The stages either side of this one are live — use the rail above to move between them.
        </p>
      </main>
    </div>
  );
}
