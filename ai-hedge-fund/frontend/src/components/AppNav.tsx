import { useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import { MemberBadge } from "@/components/MemberBadge";
import { TickerBar } from "@/components/TickerBar";
import { SECTIONS, sectionFor, type SectionKey } from "@/lib/sections";
import { useTicker } from "@/lib/ticker-context";
import { useTheme } from "@/lib/theme";

/**
 * Daylight / dark. A word rather than an icon, because a sun-and-moon pair has
 * to be learned and this has room for two letters — and because the label can
 * then say which way the press goes, which a glyph cannot.
 */
function ThemeToggle() {
  const { resolved, toggle } = useTheme();
  const next = resolved === "dark" ? "day" : "night";

  return (
    <button
      type="button"
      onClick={toggle}
      /* The control names its destination, so the accessible name has to as
       * well — announcing "day" while the button reads "night" is the usual
       * bug here. `aria-pressed` is deliberately absent: this is not a toggle
       * with an on state, it is a switch between two equal grounds. */
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
      className="shrink-0 border border-ink-line px-sm py-1.5 font-display text-label uppercase tracking-label text-on-ink-soft transition-colors hover:border-cobalt hover:text-bone focus-visible:border-cobalt focus-visible:outline-none"
    >
      {next}
    </button>
  );
}

export type AppNavActive =
  | "home"
  | "find"
  | "evaluate"
  | "manage"
  | "plan"
  | "research"
  | "screeners"
  | "breadth"
  | "optimize"
  | "portfolio"
  | "decide"
  | "autoresearch"
  | "capture"
  | "setup";

/**
 * Fallback only. Maps a caller's own screen name to the section it sits in,
 * for the cases `sectionFor` cannot answer from the path. Keys absent here
 * simply fall through to "no section highlighted", which is correct for
 * anything outside the desk.
 */
const SECTION_FOR_ACTIVE: Partial<Record<AppNavActive, SectionKey>> = {
  find: "find",
  screeners: "find",
  evaluate: "evaluate",
  plan: "evaluate",
  research: "evaluate",
  capture: "evaluate",
  decide: "evaluate",
  manage: "manage",
  portfolio: "manage",
  breadth: "manage",
  optimize: "manage",
  autoresearch: "manage",
  setup: "setup",
};

type Props = {
  active: AppNavActive;
  /** Optional right side: e.g. a data-source tagline. */
  end?: React.ReactNode;
};

/**
 * Application chrome: where you are, and the three other places you could be.
 *
 * This was nine equal links, then a search field plus an "Other ▾" disclosure
 * listing seven unrelated screens. Both versions asked the same bad question
 * at the top of every window — "which of these words is the thing you want?"
 * — and neither grouped them by anything a user cares about.
 *
 * It now carries the four sections from `sections.ts`, which are the four
 * things you can be doing here. The one you are inside is marked, including
 * when you are several screens deep: standing on stage 05 of a company
 * lights Evaluate, because that is what you are doing.
 *
 * `active` is still accepted and still names the caller's own screen, so
 * every existing view compiles unchanged. It is now only a fallback — the
 * section is derived from the URL, which cannot go stale the way a hand-
 * passed prop does.
 */

export function AppNav({ active, end }: Props) {
  const { goTo } = useTicker();
  const location = useLocation();
  const [draft, setDraft] = useState("");

  /* The URL is the authority, not the prop. A screen that passes a stale
   * `active` — or a new route whose author forgot to pass one — still lights
   * the right section, because `sectionFor` reads the path. The prop is the
   * fallback for the hubs, whose own paths (`/find`, `/manage`) resolve
   * anyway, and for anything mounted outside the router in a test. */
  const current: SectionKey | null =
    sectionFor(location.pathname) ??
    (SECTION_FOR_ACTIVE[active] ?? null);

  const search = (e: FormEvent) => {
    e.preventDefault();
    const clean = draft.trim();
    if (!clean) return;
    goTo(clean);
    setDraft("");
  };

  return (
    <div className="sticky top-0 z-30 bg-ink/95 backdrop-blur-sm">
      <nav className="border-b border-ink-line">
        {/* Wraps on a phone. This row carries five controls — wordmark,
          * search, open, membership, theme — which fit on one line with a
          * cursor and do not once every control is a 44px touch target.
          * Unwrapped they overlapped each other rather than overflowing, so
          * "OPEN" rendered on top of "NIGHT".
          *
          * `gap-x`/`gap-y` differ on purpose: a wrapped second row needs
          * vertical breathing room that the single-row desktop case does not. */}
        <div className="flex flex-wrap items-center gap-x-md gap-y-xs px-md py-sm sm:flex-nowrap sm:px-lg">
          <Link
            to="/"
            className="shrink-0 font-display text-mark tracking-marker text-bone transition-colors hover:text-oxide"
            title="Back to the landing page"
          >
            MJ
          </Link>

          <form
            onSubmit={search}
            className="flex min-w-0 grow items-center gap-xs"
          >
            <label htmlFor="ticker-search" className="sr-only">
              Search a ticker
            </label>
            <input
              id="ticker-search"
              value={draft}
              onChange={(e) => setDraft(e.target.value.toUpperCase())}
              placeholder="Search a ticker"
              autoComplete="off"
              spellCheck={false}
              className="w-full max-w-[280px] border border-ink-line bg-ink px-sm py-1.5 font-display text-label tracking-label text-bone outline-none transition-colors placeholder:text-on-ink-faint focus:border-cobalt"
            />
            <button
              type="submit"
              className="shrink-0 border border-ink-line px-sm py-1.5 font-display text-label uppercase tracking-label text-on-ink-soft transition-colors hover:border-cobalt hover:text-bone"
            >
              Open
            </button>
          </form>

          {end != null && <div className="hidden shrink-0 sm:flex">{end}</div>}

          <MemberBadge />

          <ThemeToggle />

        </div>
      </nav>

      {/* The four sections. A row of links rather than a disclosure: there
        * are four of them, they are the whole app, and hiding the shape of
        * the app behind a click is what the previous two versions of this
        * bar got wrong. Scrolls sideways on a narrow phone rather than
        * wrapping, so the chrome stays one line tall and the content keeps
        * the screen. */}
      <nav
        aria-label="Sections"
        className="overflow-x-auto border-b border-ink-line"
      >
        <ul className="flex min-w-max items-stretch">
          {SECTIONS.map((s) => {
            const on = s.key === current;
            return (
              <li key={s.key}>
                <Link
                  to={s.to}
                  aria-current={on ? "page" : undefined}
                  className={`flex items-baseline gap-2xs px-md py-sm font-display text-label uppercase tracking-label transition-colors hover:text-bone ${
                    on
                      ? "border-b-2 border-cadmium text-cadmium"
                      : "border-b-2 border-transparent text-on-ink-soft"
                  }`}
                >
                  <span className="tabular text-on-ink-faint">{s.num}</span>
                  {s.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* The stage rail belongs to Evaluate and only to Evaluate. It is the
        * path through one company; on the chooser, on Find, on the portfolio
        * it is six words of someone else's workflow competing with the
        * screen you actually opened. Showing it everywhere is what made the
        * "simple first screen" impossible — the first screen had a six-stage
        * rail on it before it had any content of its own. */}
      {current === "evaluate" && <TickerBar />}
    </div>
  );
}
