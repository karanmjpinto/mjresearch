import clsx from "clsx";

/**
 * The landing page's arguments, drawn.
 *
 * The page used to make its central claim — that a figure comes from code and
 * not from the model — in about four hundred words of prose spread over eleven
 * feature cards. Prose is the wrong medium for it: the claim is a shape (who
 * hands what to whom, and in which direction), and a shape is read in one look
 * or not at all.
 *
 * These are HTML rather than SVG, following the rule in `PixelArtifacts.tsx`:
 * anything carrying words is built from real text so it stays selectable,
 * searchable, translatable and legible when a reader raises their base font
 * size. The only SVG here would have been the arrowheads, and a text glyph
 * does that job without a second coordinate system to keep in sync.
 *
 * Two actors, two colours, used consistently across all three diagrams:
 * cobalt is the language model, enamel is plain Python. Once a reader has
 * learnt that pair in the first diagram, the other two are legible without a
 * legend — which is the whole reason the colours are assigned to actors rather
 * than to steps.
 */

export type Actor = "model" | "code";

const ACTOR: Record<Actor, { label: string; hue: string }> = {
  model: { label: "Model", hue: "var(--cobalt-paper)" },
  code: { label: "Code", hue: "var(--enamel)" },
};

/**
 * Who is responsible for a step.
 *
 * A filled chip rather than coloured text: at 12px the label has to carry on a
 * linen ground from across the room, and the fill is what makes the count
 * readable at a glance — the point of the pipeline diagram is that you can see
 * six dark chips and two blue ones without reading a word.
 */
function ActorChip({ actor }: { actor: Actor }) {
  const { label, hue } = ACTOR[actor];
  return (
    <span
      className="inline-block px-xs py-[2px] font-display text-label uppercase tracking-label text-on-accent-light"
      style={{ backgroundColor: hue }}
    >
      {label}
    </span>
  );
}

/** The arrow between two stages: sideways when they sit in a row, down when stacked. */
function Hop({ caption }: { caption?: string }) {
  return (
    <div
      className="flex shrink-0 flex-row items-center gap-2xs lg:flex-col"
      aria-hidden
    >
      <span className="font-display text-mark text-on-canvas-faint lg:hidden">
        ↓
      </span>
      <span className="hidden font-display text-mark text-on-canvas-faint lg:block">
        →
      </span>
      {caption && (
        <span className="font-display text-label uppercase tracking-label text-on-canvas-faint lg:max-w-[72px] lg:text-center">
          {caption}
        </span>
      )}
    </div>
  );
}

const BOUNDARY: Array<{
  n: string;
  actor: Actor;
  title: string;
  body: string;
  hop?: string;
}> = [
  {
    n: "01",
    actor: "model",
    title: "Picks what to measure",
    body: "Reads the question, chooses metrics from a fixed list.",
    hop: "a plan",
  },
  {
    n: "02",
    actor: "code",
    title: "Works out every figure",
    body: "Plain Python functions over frozen market data.",
    hop: "results",
  },
  {
    n: "03",
    actor: "model",
    title: "Writes the thesis",
    body: "Prose over numbers it did not produce and cannot change.",
    hop: "draft",
  },
  {
    n: "04",
    actor: "code",
    title: "Checks every number",
    body: "Re-reads the draft and matches each figure to the data.",
  },
];

/**
 * The boundary: four stages, alternating between the two actors.
 *
 * The alternation is the argument. A reader who takes nothing else from the
 * page should leave knowing that the model is bracketed by code on both sides —
 * it never opens the data, and it never gets the last word on a figure.
 */
export function ModelBoundary({ className }: { className?: string }) {
  return (
    <figure className={clsx("w-full", className)}>
      <div className="flex flex-col items-stretch gap-sm lg:flex-row lg:items-stretch">
        {BOUNDARY.map((s) => (
          <div
            key={s.n}
            className="flex min-w-0 flex-col gap-sm lg:flex-1 lg:flex-row lg:items-stretch"
          >
            <div
              className="min-w-0 flex-1 border-t-2 bg-canvas/90 p-md"
              style={{ borderTopColor: ACTOR[s.actor].hue }}
            >
              <div className="flex items-center justify-between gap-sm">
                <ActorChip actor={s.actor} />
                <span
                  className="font-display text-mark tabular"
                  style={{ color: ACTOR[s.actor].hue }}
                >
                  {s.n}
                </span>
              </div>
              <h4 className="mt-sm font-sans text-body-sm font-semibold text-enamel">
                {s.title}
              </h4>
              <p className="mt-2xs text-body-xs text-on-canvas-soft">{s.body}</p>
            </div>
            {s.hop && <Hop caption={s.hop} />}
          </div>
        ))}
      </div>
      <figcaption className="mt-lg border-l-2 border-oxide-paper pl-md text-body-sm text-on-canvas-soft">
        The model never sees a value while it plans, and never works one out
        while it writes.{" "}
        <span className="marker">No figure on this site came from a model.</span>
      </figcaption>
    </figure>
  );
}

const PIPELINE_STEPS: Array<{ step: string; actor: Actor; detail: string }> = [
  { step: "Snapshot", actor: "code", detail: "Market data fetched once, then frozen" },
  { step: "Planner", actor: "model", detail: "Chooses metrics from a fixed list — sees no values" },
  { step: "Executor", actor: "code", detail: "Python works out every figure" },
  { step: "Narrator", actor: "model", detail: "Writes prose over computed results only" },
  { step: "Harness", actor: "code", detail: "Checks each claim, overrides the score if it must" },
  { step: "Record", actor: "code", detail: "Saved so the run can be replayed" },
  { step: "Size", actor: "code", detail: "Weighed against the book you already hold" },
  { step: "Decide", actor: "code", detail: "The call kept with the portfolio behind it" },
];

/**
 * The full run, as a ladder with the actor marked on every rung.
 *
 * This replaced a numbered list whose point was buried in a sentence beside it.
 * The count in the header is computed rather than typed, so adding a stage
 * cannot leave the summary claiming a ratio that is no longer true.
 */
export function PipelineLadder({ className }: { className?: string }) {
  const modelSteps = PIPELINE_STEPS.filter((s) => s.actor === "model").length;
  const codeSteps = PIPELINE_STEPS.length - modelSteps;

  return (
    <figure className={clsx("w-full", className)}>
      <div className="mb-md flex flex-wrap items-center gap-sm border-b border-enamel/20 pb-sm">
        {/* Both halves are named, not just the one the swatch strip makes
          * obvious. The strip beside this is aria-hidden — it is the same fact
          * drawn — so a reader who cannot see colour needs the model's share
          * stated here rather than inferred by subtraction. */}
        <span className="font-display text-label uppercase tracking-label text-on-canvas-faint">
          {codeSteps} of {PIPELINE_STEPS.length} stages are plain code — the
          model holds {modelSteps}
        </span>
        <span className="flex items-center gap-2xs" aria-hidden>
          {PIPELINE_STEPS.map((s, i) => (
            <span
              key={i}
              className="h-sm w-sm"
              style={{ backgroundColor: ACTOR[s.actor].hue }}
            />
          ))}
        </span>
      </div>
      <ol className="w-full">
        {PIPELINE_STEPS.map((s, i) => (
          <li
            key={s.step}
            className="grid grid-cols-[auto_1fr] items-baseline gap-x-md gap-y-2xs border-b border-enamel/12 py-sm sm:grid-cols-[auto_64px_130px_1fr]"
          >
            <span
              className="font-display text-label tabular"
              style={{ color: ACTOR[s.actor].hue }}
            >
              {String(i + 1).padStart(2, "0")}
            </span>
            <span className="row-start-1 col-start-2 sm:col-start-2">
              <ActorChip actor={s.actor} />
            </span>
            <span className="col-start-2 font-display text-label uppercase tracking-label text-enamel sm:col-start-3">
              {s.step}
            </span>
            <span className="col-start-2 text-body-sm text-on-canvas-soft sm:col-start-4">
              {s.detail}
            </span>
          </li>
        ))}
      </ol>
    </figure>
  );
}

/**
 * Why the same company is a different answer in two different portfolios.
 *
 * Features 05 and 06 of the old page spent ninety words on this and still left
 * the reader to picture it. Drawn, it needs no argument: two books, one
 * candidate, two honest answers. The bars are the existing holding in the
 * candidate's sector, which is the single variable that moves the verdict.
 */
const BOOKS: Array<{
  name: string;
  held: string;
  fill: number;
  verdict: string;
  because: string;
  hue: string;
}> = [
  {
    name: "Book A",
    held: "41% already in chips",
    fill: 41,
    verdict: "Trim to 2%",
    because: "You own this risk twice. A third helping is one bet, not three.",
    hue: "var(--oxide-paper)",
  },
  {
    name: "Book B",
    held: "4% already in chips",
    fill: 4,
    verdict: "Size to 7%",
    because: "Nothing you hold moves with it, so it lowers the book's total swing.",
    hue: "var(--verdigris-paper)",
  },
];

export function SameNameTwoBooks({ className }: { className?: string }) {
  return (
    <figure className={clsx("w-full", className)}>
      <div className="border-2 border-enamel/25 bg-canvas/90 p-md text-center">
        <span className="font-display text-label uppercase tracking-label text-on-canvas-faint">
          One candidate, scoring 78
        </span>
        <p className="mt-2xs font-sans text-body font-semibold text-enamel">
          A semiconductor company you like
        </p>
      </div>
      <div className="my-sm text-center font-display text-mark text-on-canvas-faint" aria-hidden>
        ↓
      </div>
      <div className="grid gap-sm sm:grid-cols-2">
        {BOOKS.map((b) => (
          <div
            key={b.name}
            className="border-t-2 bg-canvas/90 p-md"
            style={{ borderTopColor: b.hue }}
          >
            <div className="flex items-baseline justify-between gap-sm">
              <span className="font-display text-label uppercase tracking-label text-enamel">
                {b.name}
              </span>
              <span className="font-display text-label tabular text-on-canvas-faint">
                {b.held}
              </span>
            </div>
            {/* The one variable that moves the answer, drawn to scale. */}
            <div className="mt-sm h-sm w-full bg-enamel/12" aria-hidden>
              <div
                className="h-sm"
                style={{ width: `${b.fill}%`, backgroundColor: b.hue }}
              />
            </div>
            <p
              className="mt-md font-display text-mark uppercase tracking-label"
              style={{ color: b.hue }}
            >
              {b.verdict}
            </p>
            <p className="mt-2xs text-body-xs text-on-canvas-soft">{b.because}</p>
          </div>
        ))}
      </div>
      <figcaption className="mt-lg border-l-2 border-oxide-paper pl-md text-body-sm text-on-canvas-soft">
        Same company, same score, opposite answers.{" "}
        <span className="marker">
          Whether to own a thing depends on what you already own.
        </span>
      </figcaption>
    </figure>
  );
}
