import { useParams } from "react-router-dom";
import { AppNav } from "./AppNav";
import { ChatInput } from "./ChatInput";
import { ErrorBoundary } from "./ErrorBoundary";
import { YourLens } from "./YourLens";
import { FrameworksApplied } from "./FrameworksApplied";
import { OnePagerPanel } from "./OnePagerPanel";
import { useTicker } from "@/lib/ticker-context";

/**
 * Stage 04 — what you already know here.
 *
 * This was the one stage still behind a "coming soon" wrapper that carried a
 * list of what it would eventually do. It now does those things, so the list
 * is gone: a screen describing its own roadmap is a screen admitting it does
 * not work yet.
 *
 * Three sections, in the order they are useful:
 *
 *   What you have written   the notes that matched, and the rule that matched
 *                           each one — the part that already worked
 *   Your frameworks, run    each checklist line with this company's figure
 *                           beside it, which is the difference between a
 *                           framework being *relevant* and being *applied*
 *   A page for this name    a draft written back into the vault, so the
 *                           conclusion ends up where you will look for it
 *
 * The last one is the only place in this app that writes to disk outside its
 * own database, which is why it previews before it writes and refuses to
 * replace anything.
 */

export function YourLensView() {
  const { ticker: paramTicker } = useParams();
  const { goTo, recents } = useTicker();
  const ticker = paramTicker?.toUpperCase() ?? "";

  if (!ticker) {
    return (
      <div className="min-h-screen bg-ink">
        <AppNav active="research" />
        <main className="mx-auto max-w-3xl px-6 py-2xl">
          <h1 className="font-display text-display-sm tracking-tight text-bone">
            Your lens
          </h1>
          <p className="mt-sm max-w-[60ch] text-body-sm text-on-ink-soft">
            Your own notes are the one input here nobody else has. Pick a
            company and this shows what you have already written about it, runs
            your frameworks against its numbers, and offers to write the
            conclusion back.
          </p>
          <div className="mt-lg">
            <ChatInput
              onSubmit={goTo}
              placeholder="Which company? (e.g. AAPL)"
            />
          </div>
          {recents.length > 0 && (
            <div className="mt-md flex flex-wrap items-center gap-xs">
              <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
                Recent
              </span>
              {recents.slice(0, 6).map((r: string) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => goTo(r)}
                  className="font-display text-label text-on-ink-soft transition-colors hover:text-cadmium"
                >
                  {r}
                </button>
              ))}
            </div>
          )}
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-ink">
      <AppNav active="research" />

      <main className="mx-auto flex max-w-6xl flex-col gap-2xl px-6 py-lg">
        <header>
          <h1 className="font-display text-display-sm tracking-tight text-bone">
            {ticker}
          </h1>
          <p className="mt-2xs max-w-[72ch] text-body-sm text-on-ink-soft">
            Everything on this page comes from your own vault. Nothing here
            leaves the machine, and nothing is written to it without a press.
          </p>
        </header>

        {/* Each section is independently boundaried: the vault is a personal
         * folder that can be unmounted, half-synced or full of notes in
         * shapes nothing here anticipated, and one of those failing should
         * not take the other two down with it. */}
        <ErrorBoundary>
          <YourLens ticker={ticker} />
        </ErrorBoundary>

        <ErrorBoundary>
          <FrameworksApplied ticker={ticker} />
        </ErrorBoundary>

        <ErrorBoundary>
          <OnePagerPanel ticker={ticker} />
        </ErrorBoundary>
      </main>
    </div>
  );
}
