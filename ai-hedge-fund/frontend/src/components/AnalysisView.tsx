import { useEffect, useState } from "react";
import { InfoTip } from "./InfoTip";
import { useParams, useSearchParams } from "react-router-dom";
import { AppNav } from "./AppNav";
import { ErrorBoundary } from "./ErrorBoundary";
import { FactorsPanel } from "./FactorsPanel";
import { InvestorViews } from "./InvestorViews";
import { PlanView } from "./PlanView";
import { ChatInput } from "./ChatInput";
import { useTicker } from "@/lib/ticker-context";

/**
 * Stage 03 — what we make of the company.
 *
 * Two screens used to answer this, and nobody could say what separated them.
 * "Investor views" lived behind a button on the data screen; "Plan analysis"
 * was a stage of its own one click further on. Both take the same snapshot,
 * both hand it to the same local model, and both come back with a judgment —
 * the difference was only ever *whose* judgment, which is a tab, not a stage.
 *
 * So stage 02 is now everything measured and stage 03 is everything judged.
 * The two tabs here are the two kinds of judging:
 *
 *   Investor views — the same data read through named styles, then reconciled
 *   Evaluation     — which metrics the model chose, what they returned, and
 *                    whether its prose actually agrees with them
 *
 * Investor views is the default because it is the part someone came to read.
 * Evaluation is how you check it, which is the second question, not the first.
 *
 * Factors is the exception to "everything judged", and deliberately so. No
 * model touches it: it places the company on the JKP factor themes and shows
 * what each theme has paid. It lives here because its job is interpretive —
 * it names what kind of company the investors are arguing about — and because
 * it answers instantly while the committee is still thinking.
 */

const TABS = [
  {
    id: "views",
    label: "Investor views",
    blurb: "The same numbers read through named styles, then reconciled.",
  },
  {
    id: "evaluation",
    label: "Evaluation",
    blurb:
      "Which metrics were computed, and whether the prose agrees with them.",
  },
  {
    id: "factors",
    label: "Factors",
    blurb:
      "Where the company sits on the thirteen JKP factor themes, and what each has paid since 1926.",
  },
] as const;

type TabId = (typeof TABS)[number]["id"];

function isTab(v: string | null): v is TabId {
  return TABS.some((t) => t.id === v);
}

export function AnalysisView() {
  const { ticker: paramTicker } = useParams();
  const [params, setParams] = useSearchParams();
  const { goTo, recents } = useTicker();

  const ticker = paramTicker?.toUpperCase() ?? "";
  const raw = params.get("view");
  const tab: TabId = isTab(raw) ? raw : "views";

  /* Whether Evaluation has ever been looked at. The plan run is started by
   * this rather than by the panel mounting, so opening a ticker does not fire
   * two local model runs at once — see the note in PlanView. */
  const [seenEvaluation, setSeenEvaluation] = useState(tab === "evaluation");
  useEffect(() => {
    if (tab === "evaluation") setSeenEvaluation(true);
  }, [tab]);

  const [seenFactors, setSeenFactors] = useState(tab === "factors");
  useEffect(() => {
    if (tab === "factors") setSeenFactors(true);
  }, [tab]);

  const setTab = (next: TabId) =>
    setParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        p.set("view", next);
        return p;
      },
      { replace: true },
    );

  if (!ticker) {
    return (
      <div className="min-h-screen bg-ink">
        <AppNav active="plan" />
        <main className="mx-auto max-w-3xl px-6 py-2xl">
          <h1 className="font-display text-display-sm tracking-tight text-bone">
            Analysis
          </h1>
          <p className="mt-sm max-w-[60ch] text-body-sm text-on-ink-soft">
            Pick a company and the analysis starts on its own — investor views
            first, then the record of which numbers produced them.
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
      <AppNav active="plan" />

      <main className="mx-auto flex max-w-6xl flex-col gap-lg px-6 py-lg">
        <header>
          <h1 className="font-display text-display-sm tracking-tight text-bone">
            {ticker}
          </h1>
          <p className="mt-2xs max-w-measure text-body-sm text-on-ink-soft">
            The model chooses which metrics to compute and writes the
            conclusion. It produces no number itself — those come from Python,
            and every claim in the prose is checked against them afterwards.
          </p>
        </header>

        {/* A tablist, not a row of buttons: arrow keys move between tabs and a
         * screen reader is told how many there are and which is current. */}
        <div>
          <div
            role="tablist"
            aria-label="Analysis"
            className="flex flex-wrap gap-xs border-b border-ink-line"
          >
            {TABS.map((t) => {
              const on = t.id === tab;
              return (
                <button
                  key={t.id}
                  role="tab"
                  id={`analysis-tab-${t.id}`}
                  aria-selected={on}
                  aria-controls={`analysis-panel-${t.id}`}
                  tabIndex={on ? 0 : -1}
                  onClick={() => setTab(t.id)}
                  onKeyDown={(e) => {
                    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
                    e.preventDefault();
                    const i = TABS.findIndex((x) => x.id === tab);
                    const next =
                      e.key === "ArrowRight"
                        ? TABS[(i + 1) % TABS.length]!
                        : TABS[(i - 1 + TABS.length) % TABS.length]!;
                    setTab(next.id);
                    document.getElementById(`analysis-tab-${next.id}`)?.focus();
                  }}
                  className={`-mb-px border-b-2 px-sm py-xs font-display text-label uppercase tracking-label transition-colors focus-visible:outline-none ${
                    on
                      ? "border-cadmium text-cadmium"
                      : "border-transparent text-on-ink-soft hover:text-bone focus-visible:text-bone"
                  }`}
                >
                  {t.label}
                </button>
              );
            })}
          </div>
          <p className="mt-xs flex max-w-measure items-center gap-xs text-body-xs text-on-ink-faint">
            {TABS.find((t) => t.id === tab)?.blurb}
            <InfoTip
              term={
                tab === "views"
                  ? "investor-views"
                  : tab === "evaluation"
                    ? "evaluation"
                    : "factors"
              }
            />
          </p>
        </div>

        {/* Both panels stay mounted. The investor run takes tens of seconds,
         * and unmounting it to glance at the evaluation would throw the
         * result away — `hidden` keeps it alive and out of the page. */}
        <div
          role="tabpanel"
          id="analysis-panel-views"
          aria-labelledby="analysis-tab-views"
          hidden={tab !== "views"}
        >
          <ErrorBoundary>
            <InvestorViews ticker={ticker} />
          </ErrorBoundary>
        </div>

        <div
          role="tabpanel"
          id="analysis-panel-evaluation"
          aria-labelledby="analysis-tab-evaluation"
          hidden={tab !== "evaluation"}
        >
          <ErrorBoundary>
            <PlanView embedded autoRun={seenEvaluation} />
          </ErrorBoundary>
        </div>

        {/* Mounted only once opened: it runs no model, so there is no long
         * result to preserve, and the profile may fetch a name live. */}
        <div
          role="tabpanel"
          id="analysis-panel-factors"
          aria-labelledby="analysis-tab-factors"
          hidden={tab !== "factors"}
        >
          {seenFactors && (
            <ErrorBoundary>
              <FactorsPanel ticker={ticker} />
            </ErrorBoundary>
          )}
        </div>
      </main>
    </div>
  );
}
