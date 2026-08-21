import { useState } from "react";
import { useLocation } from "react-router-dom";
import { TICKER_ROUTES, useTicker } from "@/lib/ticker-context";

/**
 * The spine: which name you are working on, and the stages of working on it.
 *
 * Shown only when a name is active, so it stays out of the way on the portfolio
 * and screener views where there is no single subject. The current stage is
 * marked rather than hidden, so the bar doubles as a reminder of what the flow
 * is — research it, form a view, decide — which is otherwise only implied by
 * the nav order.
 */
export function TickerBar() {
  const { ticker, recents, goTo, clear } = useTicker();
  const location = useLocation();
  const [draft, setDraft] = useState("");

  if (!ticker) return null;

  const stage = TICKER_ROUTES.find((r) => location.pathname.startsWith(`/${r.key}`))?.key;

  return (
    <div className="border-b border-ink-line bg-ink-raised">
      <div className="flex flex-wrap items-center gap-md px-lg py-2xs">
        <div className="flex items-baseline gap-sm">
          <span className="font-display text-[10px] uppercase tracking-[0.16em] text-on-ink-faint">
            Working on
          </span>
          <span className="font-display text-[16px] text-cadmium">{ticker}</span>
        </div>

        <nav className="flex items-center gap-2xs" aria-label="Stages">
          {TICKER_ROUTES.map((r) => {
            const on = stage === r.key;
            return (
              <button
                key={r.key}
                type="button"
                onClick={() => goTo(ticker, r.key)}
                aria-current={on ? "page" : undefined}
                className={`px-3 py-1.5 font-display text-[11px] uppercase tracking-[0.12em] transition-colors ${
                  on ? "bg-cobalt text-bone" : "text-on-ink-faint hover:bg-ink hover:text-on-ink"
                }`}
              >
                {r.label}
              </button>
            );
          })}
        </nav>

        <form
          className="ml-auto flex items-center gap-sm"
          onSubmit={(e) => {
            e.preventDefault();
            if (draft.trim()) {
              goTo(draft, stage ?? "research");
              setDraft("");
            }
          }}
        >
          {recents.filter((r) => r !== ticker).length > 0 && (
            <div className="hidden items-center gap-2xs lg:flex">
              <span className="font-display text-[10px] uppercase tracking-[0.14em] text-on-ink-faint">
                Recent
              </span>
              {recents
                .filter((r) => r !== ticker)
                .slice(0, 4)
                .map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => goTo(r, stage ?? "research")}
                    className="px-2 py-1 font-display text-[11px] text-on-ink-faint transition-colors hover:text-cadmium"
                  >
                    {r}
                  </button>
                ))}
            </div>
          )}
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value.toUpperCase())}
            placeholder="Switch…"
            aria-label="Switch to another ticker"
            className="w-[110px] border border-ink-line bg-ink px-2 py-1 font-display text-[11px] text-bone outline-none transition-colors placeholder:text-on-ink-faint focus:border-cobalt"
          />
          <button
            type="button"
            onClick={clear}
            className="font-display text-[11px] uppercase tracking-[0.12em] text-on-ink-faint transition-colors hover:text-oxide"
            title="Stop tracking this name"
          >
            Clear
          </button>
        </form>
      </div>
    </div>
  );
}
