import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import clsx from "clsx";

/**
 * Public landing page — raw canvas, thrown paint, pixel display type, read
 * left to right like a story rather than top to bottom like a document.
 *
 * Renders entirely from static content and makes no API calls, because this is
 * what GitHub Pages serves and there is no backend behind it.
 *
 * The colour comes from Pollock's drip canvases: unbleached linen with oxide
 * red, cadmium, cobalt and a lot of enamel black thrown at it. Each chapter is
 * assigned one colour and holds it, so the page reads as one canvas rather than
 * a rainbow — the energy is in the density and the collisions, not saturation.
 *
 * Limitations get the same weight as Features on purpose. A research tool that
 * oversells its certainty is worse than one that states plainly what it cannot do.
 */

const FEATURES = [
  {
    n: "01",
    hue: "var(--oxide)",
    label: "Deterministic numbers",
    title: "The model picks the metrics. It never computes them.",
    body: "A question compiles into a typed plan — a DAG of registered Python metrics. The planner chooses what to measure and never sees a value. The executor computes. A second pass writes prose over results it did not produce.",
  },
  {
    n: "02",
    hue: "var(--cobalt)",
    label: "Verification",
    title: "Every number in the prose is checked.",
    body: "A deterministic pass re-reads the finished thesis, extracts each numeric claim and compares it against the snapshot. Claims it cannot map are reported unverifiable — never as passing.",
  },
  {
    n: "03",
    hue: "var(--cadmium)",
    label: "Reproducibility",
    title: "Runs are recorded and diffable.",
    body: "Each analysis persists its snapshot, prompts, model parameters and output. Two runs with identical inputs should agree; when they do not, the divergence is surfaced rather than averaged away.",
  },
  {
    n: "04",
    hue: "var(--verdigris)",
    label: "Provenance",
    title: "You can see which source answered.",
    body: "Providers disagree on split adjustment, fiscal alignment and currency. Every fetch records who answered, whether it came from cache, and how the payload verified — frequency, coverage, units.",
  },
  {
    n: "05",
    hue: "var(--oxide)",
    label: "Sized against your book",
    title: "Whether to own it depends on what you already hold.",
    body: "A candidate is sized against the existing portfolio, not in isolation: resulting weight, correlation to what you hold, concentration, and the effect on portfolio volatility. A volatile name can lower total risk if it moves differently.",
  },
  {
    n: "06",
    hue: "var(--cadmium)",
    label: "Decisions on the record",
    title: "The call is kept with the book it was made against.",
    body: "Weights and correlations move, so a decision reviewed a year later is judged against the portfolio as it stood — not against today's, which would mark every past call using information nobody had.",
  },
  {
    n: "07",
    hue: "var(--verdigris)",
    label: "Autoresearch",
    title: "Overnight experiments that are hard on themselves.",
    body: "Proposes one strategy at a time and judges it on a window it never saw, with the bar rising as more things are tried — because searching enough variants against one price history will always turn something up. Discarded runs stay on the log.",
  },
  {
    n: "08",
    hue: "var(--oxide)",
    label: "Methodology memory",
    title: "Corrections of method, not of answers.",
    body: "Teach it how to approach a problem and later runs apply it. Notes containing prices or scores are rejected — a stored number would be replayed onto runs where it is no longer true.",
  },
  {
    n: "09",
    hue: "var(--cobalt)",
    label: "Local first",
    title: "Runs on your machine. No API keys.",
    body: "Ollama serves the model locally, market data comes from keyless providers by default, and the portfolio lives in a SQLite file you own. Optional keys add coverage; none are required.",
  },
];

const PIPELINE = [
  { step: "Snapshot", detail: "Market data fetched once, frozen, content-addressed", hue: "var(--aluminium)" },
  { step: "Planner", detail: "Chooses metrics from a fixed catalog — sees no values", hue: "var(--cobalt)" },
  { step: "Executor", detail: "Plain Python computes every figure", hue: "var(--cadmium)" },
  { step: "Narrator", detail: "Writes prose over computed results only", hue: "var(--cobalt)" },
  { step: "Harness", detail: "Validates, verifies claims, overrides the conviction score", hue: "var(--oxide)" },
  { step: "Record", detail: "Persisted for replay and comparison", hue: "var(--aluminium)" },
  { step: "Size", detail: "Weighted against the book you already hold", hue: "var(--oxide)" },
  { step: "Decide", detail: "The call kept with the portfolio context behind it", hue: "var(--cadmium)" },
];

const LIMITATIONS = [
  ["This is not investment advice", "A research tool. Output is generated by a language model over public data and can be wrong in ways that read perfectly plausibly. Nothing here is a recommendation to buy or sell anything."],
  ["Verification has real gaps", "Numeric claims are only checked for metrics the verifier knows about. Anything outside that set counts as unverifiable, not verified. Qualitative claims are not checked at all."],
  ["Scoring bands are absolute", "Valuation scoring uses fixed thresholds rather than sector-relative ones, so a utility and a software company are judged on the same scale."],
  ["Determinism is bounded", "Sampling is greedy and seeded and every input is recorded, but providers do not guarantee identical output. Moving arithmetic out of the model narrows this — it does not eliminate it."],
  ["Data quality is inherited", "Fundamentals come from third-party providers that disagree with each other and are sometimes stale. Provenance tells you which source answered; it cannot tell you that source was right."],
  ["Committee mode is not audited", "Persona analyses run with full freedom rather than as weightings over computed dimensions, so their conviction scores are not reproducible the way the plan pipeline's are."],
];

/** Chapter ids, in reading order, for the header links and the progress rail. */
const CHAPTERS = [
  { id: "opening", label: "Start" },
  { id: "about", label: "About" },
  { id: "features", label: "Work" },
  { id: "architecture", label: "Method" },
  { id: "limitations", label: "Limits" },
  { id: "close", label: "Open" },
];

/**
 * Drives the sideways read.
 *
 * The page still scrolls vertically — the wheel, the trackpad, the spacebar and
 * the scrollbar all keep working, and so does deep linking — but a tall spacer
 * pins one screen in place and converts that vertical distance into a
 * horizontal translation of the track inside it. The mapping is deliberately
 * 1:1: one pixel of scroll is one pixel sideways, which is what lets a chapter
 * link resolve to `spacerTop + chapterOffsetInTrack` with no scaling.
 *
 * It switches itself off below `lg` and whenever the reader has asked for
 * reduced motion; the same markup then stacks vertically, so there is one copy
 * of the content rather than a desktop version and a mobile version that drift.
 */
function useHorizontalStory() {
  const spacerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const paintRef = useRef<HTMLDivElement>(null);
  const railFillRef = useRef<HTMLDivElement>(null);
  const railLabelRef = useRef<HTMLSpanElement>(null);
  const [horizontal, setHorizontal] = useState(false);
  /* Total sideways travel: how much wider the track is than the viewport. */
  const [distance, setDistance] = useState(0);
  /* The scroll position is deliberately not state. Re-rendering nine feature
   * cards, eight pipeline steps and six limitations sixty times a second to
   * move three style properties is most of a frame's budget spent on
   * reconciliation, so the frame writes to the DOM directly and React is left
   * owning only what actually changes shape: `horizontal` and `distance`. */
  const paint = useCallback((next: number, travel: number) => {
    const ratio = travel > 0 ? next / travel : 0;
    /* Stacked, the track must carry no transform at all: an identity
     * translate3d still makes it a containing block for anything fixed. */
    if (trackRef.current) {
      trackRef.current.style.transform = travel > 0 ? `translate3d(${-next}px, 0, 0)` : "";
    }
    if (paintRef.current) {
      paintRef.current.style.transform =
        travel > 0 ? `translate3d(${(-ratio * 12).toFixed(2)}vw, 0, 0)` : "";
    }
    if (railFillRef.current) railFillRef.current.style.width = `${(ratio * 100).toFixed(2)}%`;
    if (railLabelRef.current) {
      railLabelRef.current.textContent = ratio < 0.02 ? "Scroll \u2192" : `${Math.round(ratio * 100)}%`;
    }
  }, []);

  useLayoutEffect(() => {
    const wide = window.matchMedia("(min-width: 1024px)");
    const still = window.matchMedia("(prefers-reduced-motion: reduce)");
    const decide = () => setHorizontal(wide.matches && !still.matches);

    decide();
    wide.addEventListener("change", decide);
    still.addEventListener("change", decide);
    return () => {
      wide.removeEventListener("change", decide);
      still.removeEventListener("change", decide);
    };
  }, []);

  /**
   * Measured in its own pass, after the chosen layout is actually on the page.
   * Doing it in the same pass that decides the layout measures whichever one is
   * still rendered — the stacked one, on first paint — and a stacked track is
   * no wider than the viewport, so the spacer gets a height of zero and the
   * whole thing silently degrades to a single motionless screen.
   *
   * The observers watch the panels rather than the track: the track is a flex
   * container whose own box stays viewport-width no matter how much it holds,
   * so its size never changes and an observer on it would never fire.
   */
  useLayoutEffect(() => {
    const track = trackRef.current;
    if (!horizontal || !track) {
      setDistance(0);
      return;
    }

    let live = true;
    const measure = () => {
      if (live) setDistance(Math.max(0, track.scrollWidth - window.innerWidth));
    };
    measure();
    window.addEventListener("resize", measure);
    /* Web fonts land after first paint and move every column with them. The
     * promise outlives the effect, hence the guard. */
    document.fonts?.ready.then(measure);
    const observer = new ResizeObserver(measure);
    for (const panel of track.children) observer.observe(panel);

    return () => {
      live = false;
      window.removeEventListener("resize", measure);
      observer.disconnect();
    };
  }, [horizontal]);

  useEffect(() => {
    if (!horizontal || distance === 0) {
      paint(0, 0);
      return;
    }
    let frame = 0;
    const read = () => {
      frame = 0;
      const spacer = spacerRef.current;
      if (!spacer) return;
      const top = spacer.getBoundingClientRect().top + window.scrollY;
      const travelled = window.scrollY - top;
      paint(Math.min(distance, Math.max(0, travelled)), distance);
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(read);
    };
    read();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [horizontal, distance, paint]);

  /** Sends a chapter link to the scroll position that parks that chapter on screen. */
  const goTo = useCallback(
    (id: string) => {
      const target = document.getElementById(id);
      if (!target) return;
      const spacer = spacerRef.current;
      const track = trackRef.current;
      if (!horizontal || !spacer || !track || distance === 0) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      const within = target.getBoundingClientRect().left - track.getBoundingClientRect().left;
      const top = spacer.getBoundingClientRect().top + window.scrollY;
      window.scrollTo({ top: top + Math.min(distance, Math.max(0, within)), behavior: "smooth" });
    },
    [horizontal, distance],
  );

  /**
   * Tabbing reaches panels that are clipped off to the right. Left alone the
   * browser scrolls the clipping box sideways to reveal them, which desyncs the
   * track from the scrollbar and strands the reader. Undo that scroll and move
   * the page instead, so focus and the scroll position stay the same fact.
   */
  const onFocusInTrack = useCallback(
    (event: React.FocusEvent<HTMLDivElement>) => {
      const viewport = viewportRef.current;
      if (viewport) viewport.scrollLeft = 0;

      const track = trackRef.current;
      const spacer = spacerRef.current;
      if (!horizontal || !track || !spacer || distance === 0) return;

      const rect = event.target.getBoundingClientRect();
      if (rect.left >= 0 && rect.right <= window.innerWidth) return;

      const within = rect.left - track.getBoundingClientRect().left;
      const top = spacer.getBoundingClientRect().top + window.scrollY;
      const margin = window.innerWidth * 0.15;
      window.scrollTo({ top: top + Math.min(distance, Math.max(0, within - margin)) });
    },
    [horizontal, distance],
  );

  return {
    spacerRef,
    viewportRef,
    trackRef,
    paintRef,
    railFillRef,
    railLabelRef,
    horizontal,
    distance,
    goTo,
    onFocusInTrack,
  };
}

function Marker({ children, hue }: { children: React.ReactNode; hue: string }) {
  return (
    <span className="font-display text-label uppercase tracking-marker" style={{ color: hue }}>
      {children}
    </span>
  );
}

export function Landing() {
  const { spacerRef, viewportRef, trackRef, paintRef, railFillRef, railLabelRef, horizontal, distance, goTo, onFocusInTrack } =
    useHorizontalStory();

  /* One band of the story. Sideways it is a full-height column sized by its
   * contents; stacked it is an ordinary section with a rule above it. */
  const band = (extra?: string) =>
    clsx(
      horizontal
        ? "flex h-full shrink-0 items-start gap-2xl px-[5vw] pt-[20vh]"
        : "flex flex-col gap-xl border-t border-ink/15 px-6 py-3xl",
      extra,
    );

  return (
    <div className="on-canvas relative min-h-screen bg-canvas font-sans text-on-canvas">
      {/* The paint. One fixed wash rather than a stack of heavy passes: it is
       * the ground the page stands on, not something body copy has to be
       * rescued from, so it stays far enough back that no panel needs an
       * opaque shield to stay readable. It drifts a little against the
       * sideways read — bounded by the layer's own overhang, so it can never
       * run past its own edge however long the track gets. */}
      <div aria-hidden className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div
          ref={paintRef}
          className="absolute -left-[14vw] top-0 h-[135vh] w-[128vw] bg-cover bg-top opacity-[0.2] mix-blend-multiply"
          style={{ backgroundImage: "url(/splatter.svg)" }}
        />
      </div>
      {/* Linen tooth, so the ground doesn't read as flat digital paper. */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 z-0 opacity-[0.5]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, transparent 0 3px, rgba(31,27,23,0.02) 3px 4px), repeating-linear-gradient(90deg, transparent 0 3px, rgba(31,27,23,0.02) 3px 4px)",
        }}
      />

      <div className="relative z-10">
        <header
          className={clsx(
            "z-30 border-b border-on-canvas/15 bg-canvas/85 backdrop-blur-sm",
            horizontal ? "fixed inset-x-0 top-0" : "sticky top-0",
          )}
        >
          <nav className="mx-auto flex max-w-[1400px] items-center justify-between px-6 py-4">
            <span className="font-display text-sm uppercase tracking-marker text-on-canvas">
              MJ&nbsp;Research
            </span>
            <div className="flex items-center gap-7 font-display text-label uppercase tracking-marker">
              {CHAPTERS.slice(1, -1).map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => goTo(c.id)}
                  className="hidden text-on-canvas transition-colors hover:text-oxide sm:block"
                >
                  {c.label}
                </button>
              ))}
              <Link to="/dashboard" className="bg-ink px-4 py-2 text-bone transition-colors hover:bg-oxide">
                Open&nbsp;→
              </Link>
            </div>
          </nav>
        </header>

        {/* The spacer converts vertical scroll into sideways travel. Stacked,
         * it is just a wrapper with no height of its own. */}
        <div
          ref={spacerRef}
          style={horizontal && distance > 0 ? { height: `calc(${distance}px + 100vh)` } : undefined}
        >
          <div
            ref={viewportRef}
            onFocusCapture={onFocusInTrack}
            className={clsx(horizontal && "sticky top-0 h-screen overflow-hidden")}
          >
            <main
              ref={trackRef}
              className={clsx(
                horizontal ? "flex h-full items-stretch will-change-transform" : "mx-auto max-w-6xl",
              )}
            >
              {/* Opening */}
              <section
                id="opening"
                className={clsx(
                  horizontal
                    ? "flex h-full w-screen shrink-0 items-center gap-2xl px-[5vw]"
                    : "flex flex-col gap-xl px-6 pb-3xl pt-4xl",
                )}
              >
                <div className={clsx(horizontal ? "max-w-[46vw]" : "max-w-full")}>
                  <Marker hue="var(--oxide)">Local-first equity research</Marker>
                  <h1 className="mt-lg font-display text-[clamp(38px,6vw,72px)] leading-[1.02] tracking-tight text-ink">
                    Numbers from code.
                    <br />
                    <span className="text-oxide">Not from the model.</span>
                  </h1>
                  <p className="mt-xl max-w-[58ch] text-body-lg text-on-canvas-soft">
                    Most AI research tools hand a language model a pile of data and ask for a verdict,
                    which makes every figure in the answer a token prediction. This one compiles the
                    question into a typed program, computes the figures in Python, and lets the model
                    write only over results it did not produce.
                  </p>
                  <div className="mt-2xl flex flex-wrap items-center gap-sm font-display text-label uppercase tracking-marker">
                    <Link
                      to="/dashboard"
                      className="bg-ink px-6 py-3.5 text-bone transition-all duration-300 ease-out-expo hover:bg-oxide"
                    >
                      Open the app
                    </Link>
                    <a
                      href="https://github.com/karanmjpinto/ai-hedge-fund"
                      target="_blank"
                      rel="noreferrer"
                      className="border-2 border-ink px-6 py-3.5 text-ink transition-colors hover:bg-ink hover:text-bone"
                    >
                      Source
                    </a>
                  </div>
                </div>

                {/* Studio placard, deliberately off the main column. */}
                <aside className={clsx("shrink-0", horizontal ? "w-[280px] self-end pb-[12vh]" : "max-w-[320px]")}>
                  <div className="mb-sm h-[2px] w-full bg-ink" />
                  <Marker hue="var(--on-canvas-faint)">Runs where you are</Marker>
                  <p className="mt-sm text-body-xs text-on-canvas-soft">
                    Requires a local backend and{" "}
                    <a
                      href="https://ollama.com"
                      target="_blank"
                      rel="noreferrer"
                      className="text-oxide underline decoration-oxide/40 underline-offset-4 transition-colors hover:decoration-oxide"
                    >
                      Ollama
                    </a>
                    . Nothing is hosted — your portfolio and your model stay on your machine.
                  </p>
                </aside>
              </section>

              {/* About */}
              <section id="about" className={band()}>
                <div className={clsx(horizontal && "w-[360px] shrink-0")}>
                  <div className="mb-md h-[3px] w-16 bg-cobalt" />
                  <Marker hue="var(--cobalt)">Chapter one</Marker>
                  <h2 className="mt-sm font-display text-chapter tracking-tight text-ink">
                    What this is
                  </h2>
                </div>
                <div className={clsx("gap-lg", horizontal ? "flex w-[720px] shrink-0" : "grid md:grid-cols-2")}>
                  <p className="text-body text-on-canvas-soft">
                    A research and portfolio workstation for a single investor. It pulls market data
                    from several providers with fallback and caching, keeps a persistent book in
                    SQLite, runs rule-based backtests and portfolio construction, and writes
                    investment theses with a language model running locally.
                  </p>
                  <p className="text-body text-on-canvas-soft">
                    The goal is not a smarter model. It is a harness around the model good enough
                    that its output can be checked, repeated and argued with — so when an answer is
                    wrong you can tell, and fix the method rather than the number.
                  </p>
                </div>
              </section>

              {/* Features */}
              <section id="features" className={band()}>
                <div className={clsx(horizontal && "w-[360px] shrink-0")}>
                  <div className="mb-md h-[3px] w-16 bg-oxide" />
                  <Marker hue="var(--oxide)">Chapter two</Marker>
                  <h2 className="mt-sm font-display text-chapter tracking-tight text-ink">
                    What it does
                  </h2>
                  <p className="mt-lg max-w-[34ch] text-body-sm text-on-canvas-soft">
                    Nine things, in the order they matter. The first two are the whole argument; the
                    rest are what it takes to make them hold up in practice.
                  </p>
                </div>
                <div className={clsx(horizontal ? "flex gap-lg" : "grid gap-px bg-ink/15 sm:grid-cols-2")}>
                  {FEATURES.map((f) => (
                    <article
                      key={f.n}
                      className={clsx(
                        "group border-t-2 bg-canvas/90 p-xl backdrop-blur-[1px] transition-colors duration-300 ease-out-quart hover:bg-canvas-deep",
                        horizontal && "w-[340px] shrink-0",
                      )}
                      style={{ borderTopColor: f.hue }}
                    >
                      <div className="flex items-baseline gap-sm">
                        <span
                          className="font-display text-[28px] leading-none transition-transform duration-300 ease-out-expo group-hover:-translate-y-0.5"
                          style={{ color: f.hue }}
                        >
                          {f.n}
                        </span>
                        <Marker hue="var(--on-canvas-faint)">{f.label}</Marker>
                      </div>
                      <h3 className="mt-md text-title-sm font-semibold text-ink">{f.title}</h3>
                      <p className="mt-sm max-w-[52ch] text-body-sm text-on-canvas-soft">
                        {f.body}
                      </p>
                    </article>
                  ))}
                </div>
              </section>

              {/* Architecture */}
              <section id="architecture" className={band()}>
                <div className={clsx(horizontal && "w-[360px] shrink-0")}>
                  <div className="mb-md h-[3px] w-16 bg-cadmium" />
                  <Marker hue="var(--cadmium)">Chapter three</Marker>
                  <h2 className="mt-sm font-display text-chapter tracking-tight text-ink">
                    How a question
                    <br />
                    becomes an answer
                  </h2>
                  <p className="mt-lg max-w-[34ch] text-body-sm text-on-canvas-soft">
                    The model appears twice, in two narrow roles, and is never the source of a
                    figure. When the plan computes a conviction score it replaces whatever the
                    narrator wrote — and says so.
                  </p>
                </div>

                {/* Sideways the pipeline is a timeline on a rule, which is what
                 * it always was; stacked it falls back to a numbered list. */}
                <ol className={clsx(horizontal ? "flex items-start" : "w-full")}>
                  {PIPELINE.map((p, i) => (
                    <li
                      key={p.step}
                      className={clsx(
                        horizontal
                          ? "w-[210px] shrink-0 border-t-2 border-ink/25 pt-md"
                          : "grid grid-cols-[auto_1fr] items-baseline gap-x-md gap-y-2xs border-b border-ink/12 py-md first:border-t first:border-ink/12 sm:grid-cols-[auto_140px_1fr]",
                      )}
                    >
                      <span
                        className={clsx("font-display text-label tabular", horizontal && "block pr-lg")}
                        style={{ color: p.hue }}
                      >
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span
                        className={clsx(
                          "font-display text-body-xs uppercase tracking-label text-ink",
                          horizontal && "mt-2xs block pr-lg",
                        )}
                      >
                        {p.step}
                      </span>
                      <span
                        className={clsx(
                          "text-body-sm text-on-canvas-soft",
                          horizontal ? "mt-sm block pr-lg" : "col-start-2 sm:col-start-3",
                        )}
                      >
                        {p.detail}
                      </span>
                    </li>
                  ))}
                </ol>
              </section>

              {/* Limitations */}
              <section id="limitations" className={band()}>
                <div className={clsx(horizontal && "w-[360px] shrink-0")}>
                  <div className="mb-md h-[3px] w-16 bg-oxide" />
                  <Marker hue="var(--oxide)">Chapter four</Marker>
                  <h2 className="mt-sm font-display text-chapter tracking-tight text-ink">
                    What it does not do
                  </h2>
                  <p className="mt-lg max-w-[34ch] text-body-sm text-on-canvas-soft">
                    Read this part. It carries the same weight as the chapter before it.
                  </p>
                </div>
                <div className={clsx(horizontal ? "flex gap-xl" : "grid gap-x-2xl gap-y-xl md:grid-cols-2")}>
                  {LIMITATIONS.map(([title, body], i) => (
                    <div
                      key={title}
                      className={clsx("grid grid-cols-[auto_1fr] gap-md", horizontal && "w-[300px] shrink-0")}
                    >
                      <span className="font-display text-label tabular text-oxide">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <div>
                        <h3 className="text-title-xs font-semibold text-ink">{title}</h3>
                        <p className="mt-2xs max-w-[52ch] text-body-sm text-on-canvas-soft">
                          {body}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              {/* Close */}
              <section
                id="close"
                className={clsx(
                  horizontal
                    ? "flex h-full w-screen shrink-0 flex-col justify-center px-[5vw]"
                    : "flex flex-col gap-xl border-t border-ink/15 px-6 py-3xl",
                )}
              >
                <Marker hue="var(--oxide)">End of the read</Marker>
                <h2 className="mt-lg max-w-[18ch] font-display text-[clamp(30px,4.5vw,56px)] leading-[1.05] tracking-tight text-ink">
                  Now go and argue with it.
                </h2>
                <div className="mt-2xl flex flex-wrap items-center gap-sm font-display text-label uppercase tracking-marker">
                  <Link
                    to="/dashboard"
                    className="bg-ink px-6 py-3.5 text-bone transition-all duration-300 ease-out-expo hover:bg-oxide"
                  >
                    Open the app
                  </Link>
                  <a
                    href="https://github.com/karanmjpinto/ai-hedge-fund"
                    target="_blank"
                    rel="noreferrer"
                    className="border-2 border-ink px-6 py-3.5 text-ink transition-colors hover:bg-ink hover:text-bone"
                  >
                    Source
                  </a>
                </div>
              </section>
            </main>

            {/* Progress rail. Only meaningful while the read is sideways —
             * stacked, the browser's own scrollbar already says this. */}
            {horizontal && distance > 0 && (
              <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 px-[5vw] pb-6">
                <div className="flex items-center gap-md">
                  <span
                    ref={railLabelRef}
                    className="font-display text-label uppercase tracking-label text-on-canvas-faint"
                  >
                    Scroll →
                  </span>
                  <div className="h-px flex-1 bg-ink/20">
                    <div ref={railFillRef} className="h-px w-0 bg-oxide" />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <footer className="relative z-10 border-t border-ink/20 bg-canvas py-xl">
          <div className="mx-auto flex max-w-6xl flex-col gap-sm px-6 font-display text-label uppercase tracking-marker text-on-canvas-faint sm:flex-row sm:items-center sm:justify-between">
            <span>A personal research tool — not investment advice</span>
            <a
              href="https://github.com/karanmjpinto/ai-hedge-fund"
              target="_blank"
              rel="noreferrer"
              className="transition-colors hover:text-oxide"
            >
              github.com/karanmjpinto
            </a>
          </div>
        </footer>
      </div>
    </div>
  );
}
