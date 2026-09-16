import { useLocation } from "react-router-dom";
import {
  DESTINATIONS,
  STAGES,
  stageFor,
  type DestinationKey,
} from "@/lib/flow";
import { useTicker } from "@/lib/ticker-context";

/**
 * The spine: which company you are working on, and how far through you are.
 *
 * Shown only when a name is active, so it stays out of the way on the portfolio
 * and screener views where there is no single subject. Stage 01 is the symbol
 * itself — choosing the company is the first stage, and it is answered the
 * moment there is a symbol, so rendering it as a link to nowhere would be a
 * lie. The remaining five are the path, marked rather than hidden, so the bar
 * doubles as a reminder of what the work is.
 *
 * The two unbuilt stages stay visible and carry a word saying so. Hiding them
 * would make the flow look shorter than it is; disabling them with colour
 * alone would say nothing to a reader who cannot see the colour.
 */
export function TickerBar() {
  const { ticker, recents, goTo, clear } = useTicker();
  const location = useLocation();

  if (!ticker) return null;

  const current = stageFor(location.pathname);
  const entry = STAGES[0];
  const others = recents.filter((r) => r !== ticker).slice(0, 4);

  // Switching to a recent name keeps you on the stage you were reading, so the
  // comparison you were making carries across. Off the flow, start at the top.
  const recentTarget: DestinationKey =
    current && current !== "ticker" ? current : "data";

  return (
    <div className="border-b border-ink-line bg-ink-raised">
      <div className="flex flex-wrap items-center gap-md px-lg py-2xs">
        <div className="flex items-baseline gap-xs">
          <span className="font-display text-label tracking-label text-on-ink-faint">
            {entry.num}
          </span>
          <span className="font-display text-mark text-cadmium">{ticker}</span>
        </div>

        <nav
          className="scrollbar-none flex min-w-0 items-center gap-2xs overflow-x-auto"
          aria-label="Stages"
        >
          {DESTINATIONS.map((s) => {
            const on = current === s.key;
            const planned = s.status === "planned";
            return (
              <button
                key={s.key}
                type="button"
                onClick={() => goTo(ticker, s.key)}
                aria-current={on ? "page" : undefined}
                // The number and the "soon" marker are separate spans, so the
                // announced name would otherwise run together as "01 Story
                // soon". Spelling it out also puts the unbuilt state in the
                // accessible name rather than leaving it to a visual marker.
                aria-label={`Stage ${s.num}: ${s.label}${planned ? " — not built yet" : ""}`}
                title={s.question}
                className={`shrink-0 px-3 py-1.5 font-display text-label uppercase tracking-label transition-colors ${
                  on
                    ? "bg-cobalt text-on-accent-light"
                    : "text-on-ink-faint hover:bg-ink hover:text-on-ink"
                }`}
              >
                <span className="mr-2xs text-on-ink-faint">{s.num}</span>
                {s.label}
                {planned && (
                  <span className="ml-2xs normal-case tracking-normal text-on-ink-faint">
                    soon
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-sm">
          {others.length > 0 && (
            <div className="hidden items-center gap-2xs lg:flex">
              <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
                Recent
              </span>
              {others.map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => goTo(r, recentTarget)}
                  className="px-2 py-1 font-display text-label text-on-ink-faint transition-colors hover:text-cadmium"
                >
                  {r}
                </button>
              ))}
            </div>
          )}
          <button
            type="button"
            onClick={clear}
            aria-label={`Stop tracking ${ticker}`}
            className="font-display text-label uppercase tracking-label text-on-ink-faint transition-colors hover:text-oxide"
            title="Stop tracking this name"
          >
            Clear
          </button>
        </div>
      </div>
    </div>
  );
}
