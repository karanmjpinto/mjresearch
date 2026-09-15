import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { TickerBar } from "@/components/TickerBar";
import { OTHER_DESTINATIONS } from "@/lib/flow";
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
  | "plan"
  | "research"
  | "screeners"
  | "optimize"
  | "portfolio"
  | "decide"
  | "autoresearch"
  | "setup";

/**
 * Application chrome: a way in, and a way to everything else.
 *
 * This used to be nine equal links, which made a screener and the middle of a
 * research flow look like the same kind of thing. They are not. The work is
 * one company at a time, so the bar now carries only the entry to that — a
 * search field — and the stage rail below it. The six screens that are not
 * about a single name live behind one disclosure, reachable in two clicks
 * instead of permanently occupying the top of the window.
 *
 * `active` is still accepted, and still names the caller's own screen, so all
 * nine views compile unchanged. It is used to label the menu with where you
 * already are rather than to paint an underline.
 */

type Props = {
  active: AppNavActive;
  /** Optional right side: e.g. a data-source tagline. */
  end?: React.ReactNode;
};

export function AppNav({ active, end }: Props) {
  const { goTo } = useTicker();
  const [draft, setDraft] = useState("");

  const here = OTHER_DESTINATIONS.find((d) => d.key === active);

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
        <div className="flex items-center gap-md px-lg py-sm">
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

          <ThemeToggle />

          <details className="relative shrink-0 [&>summary::-webkit-details-marker]:hidden">
            <summary
              aria-label="Other sections"
              className="cursor-pointer list-none border border-ink-line px-sm py-1.5 font-display text-label uppercase tracking-label text-on-ink-soft transition-colors hover:border-cobalt hover:text-bone"
            >
              {here ? `Other · ${here.label}` : "Other"} ▾
            </summary>
            {/* A landmark inside the disclosure, so a screen reader is told these
                are navigation links rather than arbitrary revealed content. */}
            <nav
              aria-label="Other sections"
              className="absolute right-0 z-40 mt-2xs min-w-[180px] border border-ink-line bg-ink-raised py-2xs"
            >
              <ul>
                {OTHER_DESTINATIONS.map((d) => {
                  const on = d.key === active;
                  return (
                    <li key={d.key}>
                      <Link
                        to={d.to}
                        aria-current={on ? "page" : undefined}
                        className={`block px-sm py-1.5 font-display text-label uppercase tracking-label transition-colors hover:bg-ink hover:text-bone ${
                          on ? "text-cadmium" : "text-on-ink-soft"
                        }`}
                      >
                        {d.label}
                        {on && (
                          <span className="ml-2xs text-on-ink-faint">
                            · here
                          </span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </nav>
          </details>
        </div>
      </nav>
      <TickerBar />
    </div>
  );
}
