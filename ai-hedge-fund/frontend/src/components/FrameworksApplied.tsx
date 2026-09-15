import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type AppliedCriterion, type AppliedFramework } from "@/lib/api";

/**
 * Your checklists with this company's numbers beside every line.
 *
 * Stage 04 could already say which of your frameworks touch a name. That is
 * the easy half — being told "your quality checklist is relevant here" is a
 * reminder, not an answer. This puts the figure next to the line.
 *
 * The four verdicts are deliberately four and not two, and the visual weight
 * follows that. `met` and `missed` are answers. `judgment` is a line asking
 * for a view, which no amount of data settles. `unmatched` is an admission
 * that nothing on hand speaks to it.
 *
 * Collapsing the last two into "fail" is the tempting simplification and the
 * dishonest one: it would turn an absent number into a black mark against the
 * company. So the checkable lines are counted in the header and the rest are
 * shown plainly beneath, and a framework where nothing is checkable says so
 * instead of scoring zero.
 */

const TONE: Record<
  AppliedCriterion["verdict"],
  { dot: string; text: string; word: string }
> = {
  met: { dot: "bg-verdigris", text: "text-verdigris", word: "met" },
  missed: { dot: "bg-oxide", text: "text-oxide", word: "missed" },
  judgment: { dot: "bg-cadmium", text: "text-cadmium", word: "your call" },
  unmatched: {
    dot: "bg-ink-line",
    text: "text-on-ink-faint",
    word: "no figure",
  },
};

/** Answers first, then the lines that need a view, then the gaps. */
const ORDER: AppliedCriterion["verdict"][] = [
  "missed",
  "met",
  "judgment",
  "unmatched",
];

function CriterionRow({ c }: { c: AppliedCriterion }) {
  const tone = TONE[c.verdict];
  return (
    <li className="flex items-baseline gap-sm border-t border-ink-line py-xs first:border-t-0">
      <span
        aria-hidden="true"
        className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${tone.dot}`}
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-sm gap-y-2xs">
          <span className="text-body-sm text-on-ink">{c.text}</span>
          <span
            className={`font-display text-label uppercase tracking-label ${tone.text}`}
          >
            {tone.word}
          </span>
          {c.display && (
            <span className="font-display text-label tabular text-bone">
              {c.display}
            </span>
          )}
        </div>
        <p className="mt-2xs max-w-[72ch] text-body-xs text-on-ink-faint">
          {c.because}
        </p>
      </div>
    </li>
  );
}

function FrameworkCard({ fw }: { fw: AppliedFramework }) {
  // Collapsed when there is nothing checkable: the header already carries the
  // finding, and twenty-two unmatched lines is a wall, not information.
  const [open, setOpen] = useState(fw.answerable > 0);
  const sorted = [...fw.criteria].sort(
    (a, b) => ORDER.indexOf(a.verdict) - ORDER.indexOf(b.verdict),
  );

  return (
    <div className="border border-ink-line bg-ink-raised shadow-elev-1">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full flex-wrap items-baseline justify-between gap-sm p-md text-left transition-colors hover:bg-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-cobalt"
      >
        <span className="min-w-0">
          <span className="block font-display text-mark text-bone">
            {fw.title}
          </span>
          <span className="mt-2xs block max-w-[72ch] text-body-xs text-on-ink-soft">
            {fw.finding}
          </span>
        </span>
        <span className="flex shrink-0 items-baseline gap-sm">
          {/* Counts, not a score out of ten. A framework with two checkable
           * lines has no meaningful denominator. */}
          {ORDER.map((v) =>
            fw.counts[v] ? (
              <span
                key={v}
                className={`font-display text-label tabular ${TONE[v].text}`}
                title={TONE[v].word}
              >
                {fw.counts[v]} {TONE[v].word}
              </span>
            ) : null,
          )}
          <span
            aria-hidden="true"
            className="font-display text-label text-on-ink-faint"
          >
            {open ? "−" : "+"}
          </span>
        </span>
      </button>

      {open && (
        <ul className="border-t border-ink-line px-md pb-md">
          {sorted.map((c, i) => (
            <CriterionRow key={`${c.text}-${i}`} c={c} />
          ))}
        </ul>
      )}
    </div>
  );
}

export function FrameworksApplied({ ticker }: { ticker: string }) {
  const q = useQuery({
    queryKey: ["frameworks-applied", ticker],
    queryFn: () => api.getFrameworksApplied(ticker),
    enabled: Boolean(ticker),
    retry: false,
    staleTime: 5 * 60_000,
  });

  const d = q.data;

  return (
    <section
      className="flex flex-col gap-sm"
      aria-label="Your frameworks, applied"
    >
      <div>
        <h2 className="font-display text-label uppercase tracking-label text-on-ink-faint">
          Your frameworks, run
        </h2>
        <p className="mt-2xs max-w-[72ch] text-body-sm text-on-ink-soft">
          Not a list of which checklists are relevant — each line with this
          company&rsquo;s figure beside it, where there is one.
        </p>
      </div>

      {q.isLoading && (
        <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
          Reading your checklists…
        </p>
      )}

      {q.error && (
        <div className="border border-oxide bg-ink-raised p-md">
          <p className="text-body-sm text-on-ink-soft">
            {q.error instanceof Error
              ? q.error.message
              : "Could not read the frameworks."}
          </p>
        </div>
      )}

      {d && (
        <>
          <p className="max-w-[72ch] text-body-sm text-on-ink-soft">
            {d.finding}
          </p>
          <div className="flex flex-col gap-sm">
            {d.frameworks.map((fw) => (
              <FrameworkCard key={fw.path} fw={fw} />
            ))}
          </div>

          {/* The honest note when a vault's frameworks are conceptual rather
           * than financial. Better said out loud than left looking broken. */}
          {d.configured && d.frameworks.length > 0 && (
            <p className="max-w-[72ch] text-body-xs text-on-ink-faint">
              Lines are matched to figures by the language they use — margins,
              returns, leverage, multiples. A framework written in concepts
              rather than in numbers will come back all &ldquo;your call&rdquo;,
              which is the correct answer for it.
            </p>
          )}
        </>
      )}
    </section>
  );
}
