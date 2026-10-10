import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { Link } from "react-router-dom";
import clsx from "clsx";

import {
  DensityPlate,
  GlyphPlate,
  RegistrationMark,
  RunTape,
} from "./PixelArtifacts";
import {
  ModelBoundary,
  PipelineLadder,
  SameNameTwoBooks,
} from "./ConceptDiagrams";

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

/**
 * The three claims the page stands on, given room.
 *
 * There were eleven of these, each carrying a forty-word paragraph, and the
 * section's own introduction admitted that "the first two are the whole
 * argument". Eleven equal cards is not a list of features — it is a refusal to
 * decide which ones matter, and it pushed the argument below the fold. Three
 * lead, eight follow as one line each.
 */
const LEAD = [
  {
    n: "01",
    hue: "var(--cobalt-paper)",
    label: "Where figures come from",
    title: "The model picks the metrics. It never works them out.",
    body: "It chooses what to measure from a fixed list, then plain Python computes it. The planner never sees a value.",
  },
  {
    n: "02",
    hue: "var(--oxide-paper)",
    label: "Verification",
    title: "Every number in the thesis gets checked.",
    body: "A second pass matches each figure against the data. What it cannot match it labels unverified — never passed.",
  },
  {
    n: "03",
    hue: "var(--verdigris-paper)",
    label: "Sized against your book",
    title: "Whether to own it depends on what you already own.",
    body: "A candidate is weighed against your real portfolio: its resulting weight, its overlap, and the effect on total swing.",
  },
];

/** The other eight, at one line each — enough to tell you it is there. */
const MORE = [
  {
    n: "04",
    title: "Runs you can replay",
    body: "Every run keeps its data, prompts and settings, so two runs can be compared.",
  },
  {
    n: "05",
    title: "You see which source answered",
    body: "Providers disagree. Every fetch records who answered and how it checked out.",
  },
  {
    n: "06",
    title: "Decisions kept in context",
    body: "A year on, a call is reviewed against the portfolio as it stood that day.",
  },
  {
    n: "07",
    title: "Five screens, already run",
    body: "Multibagger, compounder, Bolton contrarian, Kiyohara's Japan handbook and Ellenbogen's two acts — computed ahead of time, and dated.",
  },
  {
    n: "08",
    title: "Seventeen investors, named tests",
    body: "Each carries the tests they are known for. Seven speak by default. Read the spread.",
  },
  {
    n: "09",
    title: "Overnight experiments",
    body: "One strategy at a time, judged on a window it never saw. Failures stay on the log.",
  },
  {
    n: "10",
    title: "It remembers method, not answers",
    body: "Teach it how to approach a problem. Notes containing numbers are rejected.",
  },
  {
    n: "11",
    title: "Local first, no API keys",
    body: "Ollama serves the model and the portfolio lives in a file you own.",
  },
];

/**
 * Kept at the same weight as the claims, and cut to the same length.
 *
 * The honesty was already the best thing on this page; the only problem was
 * that each admission ran to forty words and the longest one — the catalyst
 * note — ran to fifty. They say the same things in half the space.
 */
const LIMITATIONS = [
  [
    "Not investment advice",
    "A model wrote this over public data. It can be wrong in ways that read perfectly well. Nothing here is a recommendation.",
  ],
  [
    "The checking has gaps",
    "Only figures the checker knows about get matched. The rest are marked unverified. Qualitative claims are not checked at all.",
  ],
  [
    "One scale for every sector",
    "Valuation uses fixed thresholds, so a utility and a software company are marked against the same ruler.",
  ],
  [
    "Repeatability has a limit",
    "Inputs are pinned and recorded, but no provider promises identical output. Moving the arithmetic out of the model narrows the gap rather than closing it.",
  ],
  [
    "The data is only as good as its source",
    "Providers disagree with each other and go stale. We can tell you who answered. We cannot tell you they were right.",
  ],
  [
    "No screen checks a catalyst",
    "A passing name is a candidate for a question, not an answer. The Bolton screen says so on every row.",
  ],
  [
    "Committee mode is not audited",
    "The fifteen investors speak freely rather than scoring fixed dimensions, so their conviction numbers are not repeatable the way the pipeline's are.",
  ],
];

/** Chapter ids, in reading order, for the header links and the progress rail. */
const CHAPTERS = [
  { id: "opening", label: "Start" },
  { id: "about", label: "About" },
  { id: "features", label: "Work" },
  { id: "architecture", label: "Method" },
  { id: "limitations", label: "Limits" },
  { id: "door", label: "Door" },
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
      trackRef.current.style.transform =
        travel > 0 ? `translate3d(${-next}px, 0, 0)` : "";
    }
    if (paintRef.current) {
      paintRef.current.style.transform =
        travel > 0 ? `translate3d(${(-ratio * 12).toFixed(2)}vw, 0, 0)` : "";
    }
    if (railFillRef.current)
      railFillRef.current.style.width = `${(ratio * 100).toFixed(2)}%`;
    if (railLabelRef.current) {
      railLabelRef.current.textContent =
        ratio < 0.02 ? "Scroll \u2192" : `${Math.round(ratio * 100)}%`;
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
      const within =
        target.getBoundingClientRect().left -
        track.getBoundingClientRect().left;
      const top = spacer.getBoundingClientRect().top + window.scrollY;
      window.scrollTo({
        top: top + Math.min(distance, Math.max(0, within)),
        behavior: "smooth",
      });
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
      window.scrollTo({
        top: top + Math.min(distance, Math.max(0, within - margin)),
      });
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
    <span
      className="font-display text-label uppercase tracking-marker"
      style={{ color: hue }}
    >
      {children}
    </span>
  );
}

export function Landing() {
  const {
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
  } = useHorizontalStory();

  /* One band of the story. Sideways it is a full-height column sized by its
   * contents; stacked it is an ordinary section with a rule above it. */
  const band = (extra?: string) =>
    clsx(
      horizontal
        ? "flex h-full shrink-0 items-start gap-2xl px-[5vw] pt-[20vh]"
        : "flex flex-col gap-xl border-t border-enamel/15 px-6 py-3xl",
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
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 z-0 overflow-hidden"
      >
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
            <span className="flex items-start gap-2xs font-display text-sm uppercase tracking-marker text-on-canvas">
              <span className="selected">MJ&nbsp;Research</span>
              {/* Set as a superscript beside the mark, the way a spec sheet
               * stamps the revision it describes. */}
              <span className="text-label tabular text-on-canvas-faint">
                v0.1
              </span>
            </span>
            <div className="flex items-center gap-7 font-display text-label uppercase tracking-marker">
              {CHAPTERS.slice(1, -1).map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => goTo(c.id)}
                  /* From `lg`, not `sm`. Five chapter links plus Reference
                   * plus the Open button overran 768px and clipped the button
                   * off the right edge — and these links drive the sideways
                   * read, which only engages at `lg` anyway. */
                  className="hidden text-on-canvas transition-colors hover:text-oxide-paper lg:block"
                >
                  {c.label}
                </button>
              ))}
              {/* A real route, not a chapter — the others scroll this page,
               * this one leaves it, so it does not sit in CHAPTERS. */}
              <Link
                to="/docs"
                className="text-on-canvas transition-colors hover:text-oxide-paper"
              >
                Reference
              </Link>
              <Link
                to="/dashboard"
                className="bg-enamel px-4 py-2 text-on-accent-light transition-colors hover:bg-oxide-paper"
              >
                Open&nbsp;→
              </Link>
            </div>
          </nav>
        </header>

        {/* The spacer converts vertical scroll into sideways travel. Stacked,
         * it is just a wrapper with no height of its own. */}
        <div
          ref={spacerRef}
          style={
            horizontal && distance > 0
              ? { height: `calc(${distance}px + 100vh)` }
              : undefined
          }
        >
          <div
            ref={viewportRef}
            onFocusCapture={onFocusInTrack}
            className={clsx(
              horizontal && "sticky top-0 h-screen overflow-hidden",
            )}
          >
            <main
              ref={trackRef}
              className={clsx(
                horizontal
                  ? "flex h-full items-stretch will-change-transform"
                  : "mx-auto max-w-6xl",
              )}
            >
              {/* Opening */}
              <section
                id="opening"
                className={clsx(
                  horizontal
                    ? // The header and the progress rail are both out of flow, so
                      // `items-center` would centre against the full viewport as
                      // though neither existed. On anything shorter than about 750px
                      // — a laptop with browser chrome — the eyebrow slid under the
                      // header and the buttons collided with the rail. Padding both
                      // edges centres against the space that is actually free.
                      "flex h-full w-screen shrink-0 items-center gap-2xl px-[5vw] pb-[64px] pt-[72px]"
                    : "flex flex-col gap-xl px-6 pb-3xl pt-4xl",
                )}
              >
                <div
                  className={clsx(horizontal ? "max-w-[46vw]" : "max-w-full")}
                >
                  <Marker hue="var(--oxide-paper)">
                    Local-first equity research
                  </Marker>
                  <h1 className="mt-lg font-display text-[clamp(38px,6vw,72px)] leading-[1.02] tracking-tight text-enamel">
                    The model writes
                    <br />
                    the words.
                    <br />
                    <span className="text-oxide-paper">
                      Code does the maths.
                    </span>
                  </h1>
                  <p className="mt-xl max-w-[48ch] text-body-lg text-on-canvas-soft">
                    Ask most AI research tools a question and every figure in
                    the answer is a guess dressed as a fact. Here the figures
                    are{" "}
                    <span className="marker">worked out in Python first</span>,
                    and the model only gets to describe them.
                  </p>
                  <div className="mt-2xl flex flex-wrap items-center gap-sm font-display text-label uppercase tracking-marker">
                    <Link
                      to="/dashboard"
                      className="bg-enamel px-6 py-3.5 text-on-accent-light transition-all duration-300 ease-out-expo hover:bg-oxide-paper"
                    >
                      Open the app
                    </Link>
                    <a
                      href="https://github.com/karanmjpinto/mjresearch"
                      target="_blank"
                      rel="noreferrer"
                      className="border-2 border-enamel px-6 py-3.5 text-enamel transition-colors hover:bg-enamel hover:text-on-accent-light"
                    >
                      Source
                    </a>
                  </div>
                  {/* The old page put "Open the app" on every screen and did
                   * not mention until chapter five that there is no way in
                   * without a link. Saying it here costs one line and saves
                   * every cold visitor a locked door. */}
                  <p className="mt-md text-body-xs text-on-canvas-faint">
                    The app needs an invite link. The reference below is open to
                    everyone.
                  </p>
                </div>

                {/* The argument above, as something you can read off a slip of
                 * paper. Hidden below lg with the rest of the studio furniture:
                 * on a phone the page is a document, not a desk. */}
                <RunTape className="hidden -rotate-2 lg:block" />

                {/* Studio placard, deliberately off the main column. */}
                <aside
                  className={clsx(
                    "shrink-0",
                    horizontal
                      ? "w-[280px] self-end pb-[12vh]"
                      : "max-w-[320px]",
                  )}
                >
                  <div className="mb-sm h-[2px] w-full bg-enamel" />
                  <Marker hue="var(--on-canvas-faint)">
                    Runs where you are
                  </Marker>
                  <p className="mt-sm text-body-xs text-on-canvas-soft">
                    Requires a local backend and{" "}
                    <a
                      href="https://ollama.com"
                      target="_blank"
                      rel="noreferrer"
                      className="text-oxide-paper underline decoration-oxide-paper/40 underline-offset-4 transition-colors hover:decoration-oxide-paper"
                    >
                      Ollama
                    </a>
                    . Nothing is hosted — your portfolio and your model stay on
                    your machine.
                  </p>
                </aside>
              </section>

              {/* About */}
              <section id="about" className={band()}>
                <div className={clsx(horizontal && "w-[360px] shrink-0")}>
                  <div className="mb-md h-[3px] w-16 bg-cobalt-paper" />
                  <Marker hue="var(--cobalt-paper)">One</Marker>
                  <h2 className="mt-sm font-display text-chapter tracking-tight text-enamel">
                    A research desk
                    <br />
                    that shows its work
                  </h2>
                  <p className="mt-lg max-w-[34ch] text-body-sm text-on-canvas-soft">
                    The aim is not a cleverer model. It is a frame around one
                    tight enough that you can check it, repeat it and argue with
                    it.
                  </p>
                </div>
                {/* Sized so the whole diagram lands inside one 1440px screen
                 * beside its heading column. A diagram whose last stage sits
                 * off the fold is a list again. */}
                <div
                  className={clsx(
                    "gap-xl",
                    horizontal
                      ? "flex w-[860px] shrink-0 flex-col"
                      : "flex flex-col",
                  )}
                >
                  <ModelBoundary />
                </div>
                <GlyphPlate className="hidden rotate-1 self-start lg:block" />
              </section>

              {/* Features */}
              <section id="features" className={band()}>
                <div className={clsx(horizontal && "w-[360px] shrink-0")}>
                  <div className="mb-md h-[3px] w-16 bg-oxide-paper" />
                  <Marker hue="var(--oxide-paper)">Two</Marker>
                  <h2 className="mt-sm font-display text-chapter tracking-tight text-enamel">
                    Three claims,
                    <br />
                    then the fine print
                  </h2>
                  <p className="mt-lg max-w-[34ch] text-body-sm text-on-canvas-soft">
                    If you read only the three below, you have the argument.
                    Eight more follow at a line each.
                  </p>
                </div>

                {/* The three that carry the page. */}
                <div
                  className={clsx(
                    horizontal
                      ? "flex gap-lg"
                      : "grid gap-px bg-enamel/15 sm:grid-cols-3",
                  )}
                >
                  {LEAD.map((f) => (
                    <article
                      key={f.n}
                      className={clsx(
                        "group border-t-2 bg-canvas/90 p-xl backdrop-blur-[1px] transition-colors duration-300 ease-out-quart hover:bg-canvas-deep",
                        horizontal && "w-[330px] shrink-0",
                      )}
                      style={{ borderTopColor: f.hue }}
                    >
                      <div className="flex items-baseline gap-sm">
                        <span
                          className="font-display text-display-sm leading-none transition-transform duration-300 ease-out-expo group-hover:-translate-y-0.5"
                          style={{ color: f.hue }}
                        >
                          {f.n}
                        </span>
                        <Marker hue="var(--on-canvas-faint)">{f.label}</Marker>
                      </div>
                      <h3 className="mt-md text-title-sm font-semibold text-enamel">
                        {f.title}
                      </h3>
                      <p className="mt-sm max-w-measure-sm text-body-sm text-on-canvas-soft">
                        {f.body}
                      </p>
                    </article>
                  ))}
                </div>

                {/* Claim 03, drawn — the one idea on the page that a reader
                 * cannot picture from a sentence. */}
                <div className={clsx(horizontal && "w-[520px] shrink-0")}>
                  <Marker hue="var(--on-canvas-faint)">Claim 03, drawn</Marker>
                  <div className="mt-md">
                    <SameNameTwoBooks />
                  </div>
                </div>

                {/* The remaining eight, deliberately quieter. */}
                <div className={clsx(horizontal && "w-[440px] shrink-0")}>
                  <Marker hue="var(--on-canvas-faint)">Also here</Marker>
                  <ul className="mt-md">
                    {MORE.map((f) => (
                      <li
                        key={f.n}
                        className="grid grid-cols-[auto_1fr] gap-x-md border-b border-enamel/12 py-sm first:border-t first:border-enamel/12"
                      >
                        <span className="font-display text-label tabular text-on-canvas-faint">
                          {f.n}
                        </span>
                        <div>
                          <h3 className="text-body-sm font-semibold text-enamel">
                            {f.title}
                          </h3>
                          <p className="mt-2xs max-w-measure-sm text-body-xs text-on-canvas-soft">
                            {f.body}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              </section>

              {/* Architecture */}
              <section id="architecture" className={band()}>
                <div className={clsx(horizontal && "w-[360px] shrink-0")}>
                  <div className="mb-md h-[3px] w-16 bg-cadmium-paper" />
                  <Marker hue="var(--cadmium-paper)">Three</Marker>
                  <h2 className="mt-sm font-display text-chapter tracking-tight text-enamel">
                    How a question
                    <br />
                    becomes an answer
                  </h2>
                  <p className="mt-lg max-w-[34ch] text-body-sm text-on-canvas-soft">
                    Eight stages. The model holds two of them. When the plan
                    works out a conviction score it replaces whatever the model
                    wrote — and says so.
                  </p>
                </div>

                {/* The ladder carries the actor on every rung, so the claim
                 * in the heading beside it is visible rather than asserted. */}
                <div className={clsx(horizontal && "w-[620px] shrink-0")}>
                  <PipelineLadder />
                </div>
                <DensityPlate className="hidden -rotate-1 self-start lg:block" />
              </section>

              {/* Limitations */}
              <section id="limitations" className={band()}>
                <div className={clsx(horizontal && "w-[360px] shrink-0")}>
                  <div className="mb-md h-[3px] w-16 bg-oxide-paper" />
                  <Marker hue="var(--oxide-paper)">Four</Marker>
                  <h2 className="mt-sm font-display text-chapter tracking-tight text-enamel">
                    {LIMITATIONS.length} ways
                    <br />
                    this can be wrong
                  </h2>
                  <p className="mt-lg max-w-[34ch] text-body-sm text-on-canvas-soft">
                    Read this part. It carries the same weight as the claims.
                  </p>
                </div>
                <div
                  className={clsx(
                    horizontal
                      ? "flex gap-xl"
                      : "grid gap-x-2xl gap-y-xl md:grid-cols-2",
                  )}
                >
                  {LIMITATIONS.map(([title, body], i) => (
                    <div
                      key={title}
                      className={clsx(
                        "grid grid-cols-[auto_1fr] gap-md",
                        horizontal && "w-[300px] shrink-0",
                      )}
                    >
                      <span className="font-display text-label tabular text-oxide-paper">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <div>
                        <h3 className="text-title-xs font-semibold text-enamel">
                          {title}
                        </h3>
                        <p className="mt-2xs max-w-[52ch] text-body-sm text-on-canvas-soft">
                          {body}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              {/* The door.
               *
               * Carries a chapter of its own rather than a line in the
               * footer, because for most people reading this page it is the
               * operative fact: everything described above happens somewhere
               * they cannot currently go. Stating that plainly is more
               * convincing than describing capability and quietly withholding
               * it — and the honest reason is money, not mystique, so the
               * chapter says so. */}
              <section id="door" className={band()}>
                <div className={clsx(horizontal && "w-[360px] shrink-0")}>
                  <div className="mb-md h-[3px] w-16 bg-cadmium-paper" />
                  <Marker hue="var(--cadmium-paper)">Five</Marker>
                  <h2 className="mt-sm font-display text-chapter tracking-tight text-enamel">
                    Why there is no
                    <br />
                    sign-up button
                  </h2>
                  <p className="mt-lg max-w-[34ch] text-body-sm text-on-canvas-soft">
                    No form, no waitlist. Three reasons, and none of them is
                    mystique.
                  </p>
                </div>
                <div
                  className={clsx(
                    horizontal
                      ? "flex gap-xl"
                      : "grid gap-x-2xl gap-y-xl md:grid-cols-3",
                  )}
                >
                  {[
                    [
                      "One link, once",
                      "A single-use link, sent by someone already inside. It opens one browser, then it is spent. Nobody follows you in on it.",
                    ],
                    [
                      "Because a seat costs money",
                      "Every run calls a paid model on my account. A seat is a standing bill with a monthly allowance against a name — which is why this is twenty people, not twenty thousand.",
                    ],
                    [
                      "Nothing is hidden",
                      "This page and the full reference are open to everyone, and the reference labels every capability as computed or merely written. The door controls who can spend, not who can read.",
                    ],
                  ].map(([title, body], i) => (
                    <div
                      key={title}
                      className={clsx(
                        "grid grid-cols-[auto_1fr] gap-md",
                        horizontal && "w-[300px] shrink-0",
                      )}
                    >
                      <span className="font-display text-label tabular text-cadmium-paper">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <div>
                        <h3 className="text-title-xs font-semibold text-enamel">
                          {title}
                        </h3>
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
                    ? "relative flex h-full w-screen shrink-0 flex-col justify-center px-[5vw]"
                    : "relative flex flex-col gap-xl border-t border-enamel/15 px-6 py-3xl",
                )}
              >
                <RegistrationMark className="absolute left-[5vw] top-[12vh] text-on-canvas-faint/50" />
                <RegistrationMark className="absolute right-[5vw] top-[12vh] text-on-canvas-faint/50" />
                <Marker hue="var(--oxide-paper)">End of the read</Marker>
                <h2 className="mt-lg max-w-[18ch] font-display text-[clamp(30px,4.5vw,56px)] leading-[1.05] tracking-tight text-enamel">
                  Now go and argue with it.
                </h2>
                <div className="mt-2xl flex flex-wrap items-center gap-sm font-display text-label uppercase tracking-marker">
                  <Link
                    to="/dashboard"
                    className="bg-enamel px-6 py-3.5 text-on-accent-light transition-all duration-300 ease-out-expo hover:bg-oxide-paper"
                  >
                    Open the app
                  </Link>
                  <Link
                    to="/docs"
                    className="border-2 border-enamel px-6 py-3.5 text-enamel transition-colors hover:bg-enamel hover:text-on-accent-light"
                  >
                    Read the reference
                  </Link>
                  <a
                    href="https://github.com/karanmjpinto/mjresearch"
                    target="_blank"
                    rel="noreferrer"
                    className="border-2 border-enamel px-6 py-3.5 text-enamel transition-colors hover:bg-enamel hover:text-on-accent-light"
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
                  <div className="h-px flex-1 bg-enamel/20">
                    <div
                      ref={railFillRef}
                      className="h-px w-0 bg-oxide-paper"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <footer className="relative z-10 border-t border-enamel/20 bg-canvas py-xl">
          <div className="mx-auto flex max-w-6xl flex-col gap-sm px-6 font-display text-label uppercase tracking-marker text-on-canvas-faint sm:flex-row sm:items-center sm:justify-between">
            <span>A personal research tool — not investment advice</span>
            <a
              href="https://github.com/karanmjpinto/mjresearch"
              target="_blank"
              rel="noreferrer"
              className="transition-colors hover:text-oxide-paper"
            >
              github.com/karanmjpinto
            </a>
          </div>
        </footer>
      </div>
    </div>
  );
}
