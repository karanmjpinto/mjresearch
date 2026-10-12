import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { AppNav } from "./AppNav";
import { STAGES } from "@/lib/flow";
import { sectionByKey } from "@/lib/sections";
import { useTicker } from "@/lib/ticker-context";

/**
 * The entry to the six-stage flow: pick a name.
 *
 * This section has no doors, because the path through one company is already
 * designed and `flow.ts` owns it. What it needs is a front door that makes
 * stage 01 — "which company?" — the only thing on screen, and then shows
 * what happens next so the commitment is legible before you make it.
 *
 * The stage list below the field is deliberately NOT links. Stage 04 with no
 * symbol chosen is not a place; offering it as one invites a click that
 * either 404s or silently picks the last ticker you looked at, and both are
 * worse than a list that reads as a preview of the path.
 */
export function EvaluateView() {
  const { goTo, recents } = useTicker();
  const [draft, setDraft] = useState("");
  const s = sectionByKey("evaluate");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const clean = draft.trim();
    if (!clean) return;
    goTo(clean);
    setDraft("");
  };

  return (
    <div className="min-h-screen bg-ink">
      <AppNav active="evaluate" />
      <main className="mx-auto max-w-4xl px-md py-xl sm:px-lg sm:py-2xl">
        <header className="mb-lg">
          <Link
            to="/app"
            className="font-display text-label uppercase tracking-marker text-on-ink-faint transition-colors hover:text-bone"
          >
            ← All sections
          </Link>
          <div className="mt-sm flex items-baseline gap-sm">
            <span className="font-display text-label tabular tracking-marker text-cadmium">
              {s.num}
            </span>
            <h1 className="font-display text-display-md text-bone">
              {s.label}
            </h1>
          </div>
          <p className="mt-xs max-w-[60ch] text-sm leading-relaxed text-on-ink-soft">
            {s.question}
          </p>
        </header>

        <form onSubmit={submit} className="mb-xl">
          <label
            htmlFor="evaluate-ticker"
            className="block font-display text-label uppercase tracking-marker text-on-ink-faint"
          >
            Which company?
          </label>
          <div className="mt-xs flex flex-wrap items-center gap-xs">
            <input
              id="evaluate-ticker"
              value={draft}
              onChange={(e) => setDraft(e.target.value.toUpperCase())}
              placeholder="e.g. STRL"
              autoComplete="off"
              spellCheck={false}
              className="w-full max-w-[320px] border border-ink-line bg-ink px-sm py-sm font-display text-mark tracking-label text-bone outline-none transition-colors placeholder:text-on-ink-faint focus:border-cobalt"
            />
            <button
              type="submit"
              className="shrink-0 border border-cobalt bg-cobalt px-md py-sm font-display text-label uppercase tracking-label text-on-accent-light transition-opacity hover:opacity-90"
            >
              Start
            </button>
          </div>

          {recents.length > 0 && (
            <div className="mt-sm flex flex-wrap items-center gap-xs">
              <span className="font-display text-label uppercase tracking-marker text-on-ink-faint">
                Recent
              </span>
              {recents.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => goTo(t)}
                  className="border border-ink-line px-sm py-1.5 font-display text-label tracking-label text-on-ink-soft transition-colors hover:border-cobalt hover:text-bone"
                >
                  {t}
                </button>
              ))}
            </div>
          )}
        </form>

        <section aria-labelledby="path-heading">
          <h2
            id="path-heading"
            className="font-display text-label uppercase tracking-marker text-on-ink-faint"
          >
            What happens next
          </h2>
          <ol className="mt-sm border-t border-ink-line">
            {STAGES.map((stage) => (
              <li
                key={stage.key}
                className="flex flex-wrap items-baseline gap-x-sm gap-y-2xs border-b border-ink-line py-sm"
              >
                <span className="font-display text-label tabular tracking-marker text-on-ink-faint">
                  {stage.num}
                </span>
                <span className="font-display text-label uppercase tracking-label text-bone">
                  {stage.label}
                </span>
                <span className="text-sm text-on-ink-soft">
                  {stage.question}
                </span>
              </li>
            ))}
          </ol>
        </section>
      </main>
    </div>
  );
}
