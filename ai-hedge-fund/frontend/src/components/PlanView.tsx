import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { AppNav } from "@/components/AppNav";
import {
  api,
  type ExecutedNode,
  type PlanResult,
  type VerifiedClaim,
} from "@/lib/api";
import { readField, type Tone } from "@/lib/field-scales";
import { formatValue } from "@/lib/format";
import {
  ClaimCompare,
  NodeReadout,
  SegmentBar,
  Track,
} from "@/components/MetricReadout";

/**
 * Plan pipeline view.
 *
 * The point of this screen is that the reasoning is inspectable. A conviction
 * score is only trustworthy if you can see which metrics produced it, what each
 * one returned, which methodology defaults were assumed, and whether the prose
 * actually agrees with the numbers. So the plan and its execution are shown as
 * primary content rather than tucked behind a disclosure.
 */

/* Stance is a decision, so it gets a solid painted block rather than a tinted
 * outline — it should be the first thing the eye lands on. */
const STANCE_STYLE: Record<string, string> = {
  BUY: "bg-verdigris text-on-accent",
  HOLD: "bg-cadmium text-on-accent",
  WATCH: "bg-cobalt text-on-accent-light",
  SELL: "bg-oxide text-on-accent-light",
};

const STATUS_DOT: Record<ExecutedNode["status"], string> = {
  ok: "bg-verdigris",
  error: "bg-oxide",
  skipped: "bg-on-ink-faint",
};

function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`border border-ink-line bg-ink-raised ${className}`}>
      {children}
    </div>
  );
}

function SectionHeading({
  children,
  hint,
  bar,
}: {
  children: React.ReactNode;
  hint?: string;
  bar?: { label: string; count: number; tone: Tone }[];
}) {
  return (
    <div className="mb-sm flex items-center justify-between gap-md">
      <h2 className="font-display text-label uppercase tracking-[0.18em] text-on-ink-faint">
        {children}
      </h2>
      <div className="flex items-center gap-sm">
        {hint && (
          <span className="font-display text-label tabular text-on-ink-faint">
            {hint}
          </span>
        )}
        {bar && <SegmentBar segments={bar} />}
      </div>
    </div>
  );
}

function VerificationBadge({
  v,
}: {
  v: NonNullable<PlanResult["verification"]>;
}) {
  const tone =
    v.status === "clean"
      ? "bg-verdigris/15 text-verdigris"
      : v.status === "mismatch"
        ? "bg-oxide/20 text-oxide"
        : "bg-ink-line text-on-ink-soft";
  const label =
    v.status === "clean"
      ? `${v.verified}/${v.checked} claims verified`
      : v.status === "mismatch"
        ? `${v.mismatched} claim${v.mismatched === 1 ? " contradicts" : "s contradict"} the data`
        : "no numeric claims made";
  return (
    <span
      className={`px-2.5 py-1.5 font-display text-label uppercase tracking-[0.12em] ${tone}`}
    >
      {label}
    </span>
  );
}

const CLAIM_TONE: Record<VerifiedClaim["verdict"], Tone> = {
  verified: "up",
  mismatch: "down",
  unverifiable: "neutral",
};

const CLAIM_RAIL: Record<Tone, string> = {
  up: "border-l-verdigris",
  down: "border-l-oxide",
  warn: "border-l-cadmium",
  neutral: "border-l-ink-line",
};

const CLAIM_TEXT: Record<Tone, string> = {
  up: "text-verdigris",
  down: "text-oxide",
  warn: "text-cadmium",
  neutral: "text-on-ink-faint",
};

/**
 * One claim the prose made, and what the data says.
 *
 * The verdict word alone asks the reader to trust the checker. Showing the
 * sentence that carried the claim, and — where they disagree — both numbers
 * drawn to a shared scale, lets them see the disagreement instead.
 */
function ClaimRow({ c }: { c: VerifiedClaim }) {
  const tone = CLAIM_TONE[c.verdict];
  const disputed = c.verdict === "mismatch" && typeof c.actual === "number";

  return (
    <li
      className={`border-l-2 border-t border-t-ink-line px-lg py-sm first:border-t-0 ${CLAIM_RAIL[tone]}`}
    >
      <div className="flex flex-wrap items-baseline gap-x-sm gap-y-2xs">
        <span
          className={`w-20 shrink-0 font-display text-label uppercase tracking-label ${CLAIM_TEXT[tone]}`}
        >
          {c.verdict}
        </span>
        <span className="w-36 shrink-0 truncate font-display text-label text-on-ink-soft">
          {c.metric}
        </span>
        <span className="font-display text-label tabular text-on-ink">
          {formatValue(c.stated)}
          {c.unit ?? ""}
        </span>
        {disputed && (
          <span className="font-display text-label tabular text-on-ink-faint">
            vs {formatValue(c.actual)}
            {c.unit ?? ""} computed
            {typeof c.delta_pct === "number" &&
              ` · off by ${formatValue(Math.abs(c.delta_pct))}%`}
          </span>
        )}
        {c.note && (
          <span className="truncate text-label text-on-ink-faint">
            {c.note}
          </span>
        )}
      </div>

      {c.excerpt && (
        <p className="mt-2xs line-clamp-2 text-xs italic leading-snug text-on-ink-faint">
          “{c.excerpt}”
        </p>
      )}

      {disputed && (
        <ClaimCompare stated={c.stated} actual={c.actual as number} />
      )}
    </li>
  );
}

/**
 * One executed metric. The node's own name and reason stay small; what it
 * computed is given the weight, because that is what the reader came for.
 */
function NodeRow({ n }: { n: ExecutedNode }) {
  return (
    <li className="border-t border-ink-line px-lg py-md first:border-t-0">
      <div className="flex items-baseline gap-sm">
        <span
          className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${STATUS_DOT[n.status]}`}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-sm gap-y-2xs">
            <span className="font-display text-[14px] text-bone">
              {n.node_id}
            </span>
            <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
              {n.metric}
            </span>
            {n.cached && (
              <span className="bg-ink-line px-1.5 py-0.5 font-display text-label uppercase tracking-wide text-on-ink-faint">
                cached
              </span>
            )}
          </div>
          {n.why && (
            <p className="mt-2xs text-xs italic text-on-ink-faint">{n.why}</p>
          )}

          {n.status === "ok" ? (
            <NodeReadout values={n.values} />
          ) : (
            <p className="mt-xs text-xs text-on-ink-faint">
              <span className="text-oxide">
                {n.status === "error" ? "did not compute" : "skipped"}
              </span>
              {n.error ? ` — ${n.error}` : ""}
            </p>
          )}
        </div>
      </div>
    </li>
  );
}

/**
 * `embedded` drops the page chrome so this can sit inside a tab on the
 * Analysis screen next to the investor views. The two answer one question —
 * what do we make of this company — and used to be two stages apart.
 */
export function PlanView({
  embedded = false,
  autoRun = false,
}: { embedded?: boolean; autoRun?: boolean } = {}) {
  const navigate = useNavigate();
  const { ticker: routeTicker } = useParams();
  const [ticker, setTicker] = useState((routeTicker ?? "").toUpperCase());
  const [question, setQuestion] = useState("");
  const [style, setStyle] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<PlanResult | null>(null);

  const run = useMutation({
    mutationFn: (body: Parameters<typeof api.runPlan>[0]) => api.runPlan(body),
    onSuccess: setResult,
  });

  const submit = (overrideAnswers?: Record<string, string>) => {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    run.mutate({
      ticker: t,
      question: question.trim() || undefined,
      style: style.trim() || undefined,
      clarification_answers:
        overrideAnswers ?? (Object.keys(answers).length ? answers : undefined),
    });
  };

  /* Embedded in the Analysis screen, this starts on its own — the reader asked
   * for the company, not for a button.
   *
   * `autoRun` is the host saying the Evaluation tab has actually been opened.
   * The panel itself is mounted from the start, because unmounting it would
   * throw away a finished run every time someone glanced at the other tab —
   * so "mounted" cannot be the trigger. Without that distinction, opening any
   * ticker would fire two thirty-second local model runs at once, and they
   * would contend for the same machine.
   *
   * `kicked` is a ref rather than state so a re-render cannot fire it twice,
   * and it is keyed to the symbol so switching company re-arms it. */
  const kicked = useRef<string | null>(null);
  useEffect(() => {
    if (!embedded || !autoRun) return;
    const t = (routeTicker ?? "").trim().toUpperCase();
    if (!t || kicked.current === t) return;
    kicked.current = t;
    submit();
  }, [embedded, autoRun, routeTicker]);

  const exec = result?.execution;
  const pending = result?.clarifications_pending ?? [];
  const verification = result?.verification;
  const overrides = result?.harness_overrides ?? [];
  const convictionReading = readField("conviction_score", result?.conviction);

  const Shell = embedded ? EmbeddedShell : PageShell;

  return (
    <Shell>
      {!embedded && (
        <header className="mb-8">
          <h1 className="font-display text-display-sm tracking-tight text-bone">
            Plan analysis
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-on-ink-faint">
            The model chooses which metrics to compute and writes the
            conclusion. It does not produce any number — those come from Python,
            and every claim in the prose is checked against the data afterwards.
          </p>
        </header>
      )}

      {/* Input */}
      <Card className="p-5">
        <div className="grid gap-4 sm:grid-cols-[160px_1fr]">
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-on-ink-faint">
              Ticker
            </span>
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              placeholder="AAPL"
              className="w-full rounded-lg border border-ink-line bg-ink px-3 py-2 font-mono text-sm uppercase text-white outline-none transition-colors placeholder:font-sans placeholder:normal-case placeholder:text-on-ink-faint focus:border-cobalt"
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-on-ink-faint">
              Question{" "}
              <span className="normal-case text-on-ink-faint">(optional)</span>
            </span>
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              placeholder="Is this attractive at current levels?"
              className="w-full rounded-lg border border-ink-line bg-ink px-3 py-2 text-sm text-white outline-none transition-colors placeholder:text-on-ink-faint focus:border-cobalt"
            />
          </label>
        </div>

        <div className="mt-4 flex flex-wrap items-end gap-4">
          <label className="block min-w-[220px] flex-1">
            <span className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-on-ink-faint">
              Style{" "}
              <span className="normal-case text-on-ink-faint">(optional)</span>
            </span>
            <input
              value={style}
              onChange={(e) => setStyle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              placeholder="deep value, quality at a reasonable price…"
              className="w-full rounded-lg border border-ink-line bg-ink px-3 py-2 text-sm text-white outline-none transition-colors placeholder:text-on-ink-faint focus:border-cobalt"
            />
          </label>
          <button
            type="button"
            onClick={() => submit()}
            disabled={!ticker.trim() || run.isPending}
            className="rounded-lg bg-cobalt px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-cobalt/80 disabled:cursor-not-allowed disabled:bg-ink-line disabled:text-on-ink-faint"
          >
            {run.isPending ? "Computing…" : "Run plan"}
          </button>
        </div>

        {run.isPending && (
          <p className="mt-4 text-xs text-on-ink-faint">
            Planning, executing metrics, then writing. A local model typically
            takes 10–30 seconds.
          </p>
        )}
      </Card>

      {run.isError && (
        <Card className="mt-5 border-oxide/30 p-5">
          <p className="text-sm text-oxide">Request failed</p>
          <p className="mt-1.5 text-xs leading-relaxed text-on-ink-soft">
            {(run.error as Error).message}
          </p>
        </Card>
      )}

      {result?.ai_error && (
        <Card className="mt-5 border-oxide/30 p-5">
          <p className="text-sm text-oxide">{result.ai_error.error}</p>
          <p className="mt-1.5 text-xs leading-relaxed text-on-ink-soft">
            {result.ai_error.message}
          </p>
        </Card>
      )}

      {result && !result.ai_error && (
        <div className="mt-8 space-y-8">
          {/* Verdict */}
          <section>
            <SectionHeading
              hint={
                result.run_uid ? `run ${result.run_uid.slice(0, 8)}` : undefined
              }
            >
              Conclusion
            </SectionHeading>
            <Card className="p-6">
              <div className="flex flex-wrap items-center gap-4">
                <div>
                  <div className="font-display text-[64px] leading-none tabular text-bone">
                    {result.conviction ?? "—"}
                    <span className="ml-1 text-[20px] text-on-ink-faint">
                      /100
                    </span>
                  </div>
                  {convictionReading ? (
                    <div className="mt-xs w-56">
                      <Track r={convictionReading} tall />
                      <div className="mt-2xs flex justify-between font-display text-label text-on-ink-faint">
                        <span>{convictionReading.ends[0]}</span>
                        <span>{convictionReading.ends[1]}</span>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-2xs text-xs text-on-ink-faint">
                      conviction, computed by the plan
                    </p>
                  )}
                </div>
                {result.stance && (
                  <span
                    className={`px-4 py-2 font-display text-[13px] uppercase tracking-[0.16em] ${
                      STANCE_STYLE[result.stance] ?? "bg-ink-line text-on-ink"
                    }`}
                  >
                    {result.stance}
                  </span>
                )}
                {verification && <VerificationBadge v={verification} />}
                {result.evaluation?.narrative_grounded === false &&
                  verification?.status === "no_claims" && (
                    <span className="rounded-md border border-cadmium/30 bg-cadmium/10 px-2.5 py-1 text-xs font-medium text-cadmium">
                      prose cites none of the computed values
                    </span>
                  )}
              </div>

              {result.analysis && (
                <p className="mt-5 border-t border-ink-line pt-5 text-sm leading-relaxed text-on-ink">
                  {result.analysis}
                </p>
              )}

              {!!result.evaluation?.notes?.length && (
                <ul className="mt-4 space-y-1.5">
                  {result.evaluation.notes.map((n) => (
                    <li key={n} className="text-xs text-cadmium/90">
                      {n}
                    </li>
                  ))}
                </ul>
              )}

              {/* A view is not the end of the work — it is the input to a
               * decision, so the next step is offered here rather than left
               * for the reader to go and find. */}
              <div className="mt-5 flex flex-wrap items-center gap-sm border-t border-ink-line pt-5">
                <button
                  type="button"
                  onClick={() =>
                    navigate(
                      `/decide/${encodeURIComponent(ticker.trim().toUpperCase())}`,
                      {
                        state: {
                          conviction: result.conviction,
                          stance: result.stance,
                          thesis: result.analysis,
                          run_uid: result.run_uid,
                        },
                      },
                    )
                  }
                  className="bg-verdigris px-5 py-2.5 font-display text-label uppercase tracking-[0.14em] text-on-accent transition-colors hover:bg-cadmium"
                >
                  Size this against my book →
                </button>
                <span className="text-xs text-on-ink-faint">
                  Carries this conviction and thesis into the decision record.
                </span>
              </div>
            </Card>
          </section>

          {/* Harness overrides */}
          {overrides.length > 0 && (
            <section>
              <SectionHeading>Harness overrides</SectionHeading>
              <Card className="p-5">
                <p className="mb-3 text-xs leading-relaxed text-on-ink-faint">
                  The model's value was discarded in favour of the computed one.
                </p>
                {overrides.map((o) => (
                  <div
                    key={o.field}
                    className="flex flex-wrap items-baseline gap-2 text-sm"
                  >
                    <span className="font-mono text-on-ink-soft">
                      {o.field}
                    </span>
                    <span className="font-mono text-on-ink-faint line-through">
                      {formatValue(o.model_said)}
                    </span>
                    <span className="text-on-ink-faint">→</span>
                    <span className="font-mono text-verdigris">
                      {formatValue(o.harness_used)}
                    </span>
                    <span className="text-xs text-on-ink-faint">
                      from {o.source}
                    </span>
                  </div>
                ))}
              </Card>
            </section>
          )}

          {/* Clarifications */}
          {pending.length > 0 && (
            <section>
              <SectionHeading>Methodology decisions</SectionHeading>
              <Card className="p-5">
                <p className="mb-4 text-xs leading-relaxed text-on-ink-faint">
                  These were answered with the recommended default. Choosing
                  differently re-runs the plan.
                </p>
                <div className="space-y-5">
                  {pending.map((c) => (
                    <div key={c.id}>
                      <p className="text-sm text-on-ink">{c.question}</p>
                      <div className="mt-2.5 flex flex-wrap gap-2">
                        {c.options.map((opt) => {
                          const chosen = (answers[c.id] ?? c.effective) === opt;
                          return (
                            <button
                              key={opt}
                              type="button"
                              onClick={() => {
                                const next = { ...answers, [c.id]: opt };
                                setAnswers(next);
                                submit(next);
                              }}
                              className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${
                                chosen
                                  ? "border-cobalt/40 bg-cobalt/10 text-cobalt"
                                  : "border-ink-line bg-ink text-on-ink-soft hover:border-on-ink-faint hover:text-on-ink"
                              }`}
                            >
                              {opt}
                              {opt === c.recommended && (
                                <span className="ml-1.5 text-label uppercase tracking-wide text-on-ink-faint">
                                  recommended
                                </span>
                              )}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            </section>
          )}

          {/* Execution */}
          {exec && (
            <section>
              <SectionHeading
                hint={`${exec.ok_count} computed · ${exec.error_count} failed · ${exec.elapsed_ms}ms`}
                bar={[
                  { label: "computed", count: exec.ok_count, tone: "up" },
                  { label: "failed", count: exec.error_count, tone: "down" },
                  {
                    label: "skipped",
                    count: exec.skipped_count,
                    tone: "neutral",
                  },
                ]}
              >
                The plan
              </SectionHeading>
              <Card>
                <ul>
                  {exec.nodes.map((n) => (
                    <NodeRow key={n.node_id} n={n} />
                  ))}
                </ul>
              </Card>
              <p className="mt-2.5 font-mono text-label text-on-ink-faint">
                plan {exec.plan_hash.slice(0, 12)} · snapshot{" "}
                {exec.snapshot_sha256.slice(0, 12)}
              </p>
            </section>
          )}

          {/* Claims */}
          {verification && verification.claims.length > 0 && (
            <section>
              <SectionHeading
                hint={`${verification.verified} verified · ${verification.mismatched} contradicted · ${verification.unverifiable} unverifiable`}
                bar={[
                  {
                    label: "verified",
                    count: verification.verified,
                    tone: "up",
                  },
                  {
                    label: "mismatch",
                    count: verification.mismatched,
                    tone: "down",
                  },
                  {
                    label: "unverifiable",
                    count: verification.unverifiable,
                    tone: "neutral",
                  },
                ]}
              >
                Claim verification
              </SectionHeading>
              <Card>
                <ul>
                  {verification.claims.map((c, i) => (
                    <ClaimRow key={`${c.metric}-${i}`} c={c} />
                  ))}
                </ul>
              </Card>
            </section>
          )}

          {/* Provenance */}
          {result.data_quality && (
            <section>
              <SectionHeading>Data sources</SectionHeading>
              <Card className="p-5">
                <p className="text-sm text-on-ink-soft">
                  Resolved from{" "}
                  <span className="font-mono text-on-ink">
                    {result.data_quality.providers_used.join(", ") ||
                      "no provider"}
                  </span>
                </p>
                {result.data_quality.warning_count > 0 ? (
                  <ul className="mt-3 space-y-1.5">
                    {result.data_quality.warnings.map((w) => (
                      <li key={w} className="text-xs text-cadmium/90">
                        {w}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-xs text-on-ink-faint">
                    No data-quality warnings on this snapshot.
                  </p>
                )}
              </Card>
            </section>
          )}
        </div>
      )}
    </Shell>
  );
}

/** Standalone: its own chrome and page width. */
function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-ink">
      <AppNav active="plan" />
      <main className="mx-auto max-w-5xl px-6 py-10">{children}</main>
    </div>
  );
}

/** Inside a tab: no nav, no page padding — the host already supplies both. */
function EmbeddedShell({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-col">{children}</div>;
}
