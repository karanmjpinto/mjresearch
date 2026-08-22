import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { AppNav } from "@/components/AppNav";
import { api, type ExecutedNode, type PlanResult, type VerifiedClaim } from "@/lib/api";

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
  BUY: "bg-verdigris text-ink",
  HOLD: "bg-cadmium text-ink",
  WATCH: "bg-cobalt text-bone",
  SELL: "bg-oxide text-bone",
};

const STATUS_DOT: Record<ExecutedNode["status"], string> = {
  ok: "bg-verdigris",
  error: "bg-oxide",
  skipped: "bg-on-ink-faint",
};

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "—";
    if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
    if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
    return Number.isInteger(v) ? String(v) : v.toFixed(2);
  }
  return String(v);
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`border border-ink-line bg-ink-raised ${className}`}>{children}</div>
  );
}

function SectionHeading({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-4">
      <h2 className="font-display text-label uppercase tracking-[0.18em] text-on-ink-faint">
        {children}
      </h2>
      {hint && <span className="font-display text-label tabular text-on-ink-faint">{hint}</span>}
    </div>
  );
}

function VerificationBadge({ v }: { v: NonNullable<PlanResult["verification"]> }) {
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
    <span className={`px-2.5 py-1.5 font-display text-label uppercase tracking-[0.12em] ${tone}`}>{label}</span>
  );
}

function ClaimRow({ c }: { c: VerifiedClaim }) {
  const tone =
    c.verdict === "verified"
      ? "text-accent-green"
      : c.verdict === "mismatch"
        ? "text-accent-red"
        : "text-gray-500";
  return (
    <li className="flex items-baseline gap-3 border-t border-border/60 px-5 py-3 first:border-t-0">
      <span className={`font-mono text-label uppercase ${tone} w-24 shrink-0`}>{c.verdict}</span>
      <span className="w-36 shrink-0 truncate font-mono text-xs text-gray-400">{c.metric}</span>
      <span className="font-mono text-xs text-gray-300">
        {formatValue(c.stated)}
        {c.verdict === "mismatch" && (
          <span className="text-gray-500"> vs {formatValue(c.actual)} in data</span>
        )}
      </span>
      {c.note && <span className="truncate text-xs text-gray-600">{c.note}</span>}
    </li>
  );
}

function NodeRow({ n }: { n: ExecutedNode }) {
  const entries = Object.entries(n.values).filter(([, v]) => v !== null && v !== undefined);
  return (
    <li className="border-t border-border/60 px-5 py-4 first:border-t-0">
      <div className="flex items-baseline gap-3">
        <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${STATUS_DOT[n.status]}`} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
            <span className="font-display text-[14px] text-bone">{n.node_id}</span>
            <span className="font-display text-label uppercase tracking-[0.1em] text-on-ink-faint">{n.metric}</span>
            {n.cached && (
              <span className="rounded bg-surface-elevated px-1.5 py-0.5 text-label uppercase tracking-wide text-gray-500">
                cached
              </span>
            )}
          </div>
          {n.why && <p className="mt-1 text-xs italic text-gray-600">{n.why}</p>}

          {n.status === "ok" ? (
            <dl className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1.5">
              {entries.map(([k, v]) => (
                <div key={k} className="flex items-baseline gap-1.5">
                  <dt className="text-[12px] text-on-ink-faint">{k}</dt>
                  <dd className="font-display text-[12px] tabular text-cadmium">{formatValue(v)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="mt-2 text-xs text-gray-500">
              <span className="text-accent-red/80">
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

export function PlanView() {
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
      clarification_answers: overrideAnswers ?? (Object.keys(answers).length ? answers : undefined),
    });
  };

  const exec = result?.execution;
  const pending = result?.clarifications_pending ?? [];
  const verification = result?.verification;
  const overrides = result?.harness_overrides ?? [];

  return (
    <div className="min-h-screen bg-surface">
      <AppNav active="plan" />

      <main className="mx-auto max-w-5xl px-6 py-10">
        <header className="mb-8">
          <h1 className="font-display text-display-sm tracking-tight text-bone">Plan analysis</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-gray-500">
            The model chooses which metrics to compute and writes the conclusion. It does not
            produce any number — those come from Python, and every claim in the prose is checked
            against the data afterwards.
          </p>
        </header>

        {/* Input */}
        <Card className="p-5">
          <div className="grid gap-4 sm:grid-cols-[160px_1fr]">
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-gray-500">
                Ticker
              </span>
              <input
                value={ticker}
                onChange={(e) => setTicker(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                placeholder="AAPL"
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 font-mono text-sm uppercase text-white outline-none transition-colors placeholder:font-sans placeholder:normal-case placeholder:text-gray-600 focus:border-accent-blue"
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-gray-500">
                Question <span className="normal-case text-gray-600">(optional)</span>
              </span>
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                placeholder="Is this attractive at current levels?"
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-white outline-none transition-colors placeholder:text-gray-600 focus:border-accent-blue"
              />
            </label>
          </div>

          <div className="mt-4 flex flex-wrap items-end gap-4">
            <label className="block min-w-[220px] flex-1">
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-gray-500">
                Style <span className="normal-case text-gray-600">(optional)</span>
              </span>
              <input
                value={style}
                onChange={(e) => setStyle(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                placeholder="deep value, quality at a reasonable price…"
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-white outline-none transition-colors placeholder:text-gray-600 focus:border-accent-blue"
              />
            </label>
            <button
              type="button"
              onClick={() => submit()}
              disabled={!ticker.trim() || run.isPending}
              className="rounded-lg bg-accent-blue px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-surface-elevated disabled:text-gray-600"
            >
              {run.isPending ? "Computing…" : "Run plan"}
            </button>
          </div>

          {run.isPending && (
            <p className="mt-4 text-xs text-gray-500">
              Planning, executing metrics, then writing. A local model typically takes 10–30
              seconds.
            </p>
          )}
        </Card>

        {run.isError && (
          <Card className="mt-5 border-accent-red/30 p-5">
            <p className="text-sm text-accent-red">Request failed</p>
            <p className="mt-1.5 text-xs leading-relaxed text-gray-400">
              {(run.error as Error).message}
            </p>
          </Card>
        )}

        {result?.ai_error && (
          <Card className="mt-5 border-accent-red/30 p-5">
            <p className="text-sm text-accent-red">{result.ai_error.error}</p>
            <p className="mt-1.5 text-xs leading-relaxed text-gray-400">
              {result.ai_error.message}
            </p>
          </Card>
        )}

        {result && !result.ai_error && (
          <div className="mt-8 space-y-8">
            {/* Verdict */}
            <section>
              <SectionHeading hint={result.run_uid ? `run ${result.run_uid.slice(0, 8)}` : undefined}>
                Conclusion
              </SectionHeading>
              <Card className="p-6">
                <div className="flex flex-wrap items-center gap-4">
                  <div>
                    <div className="font-display text-[64px] leading-none tabular text-bone">
                      {result.conviction ?? "—"}
                      <span className="ml-1 text-[20px] text-on-ink-faint">/100</span>
                    </div>
                    <p className="mt-1 text-xs text-gray-500">conviction, computed by the plan</p>
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
                      <span className="rounded-md border border-accent-yellow/30 bg-accent-yellow/10 px-2.5 py-1 text-xs font-medium text-accent-yellow">
                        prose cites none of the computed values
                      </span>
                    )}
                </div>

                {result.analysis && (
                  <p className="mt-5 border-t border-border/60 pt-5 text-sm leading-relaxed text-gray-300">
                    {result.analysis}
                  </p>
                )}

                {!!result.evaluation?.notes?.length && (
                  <ul className="mt-4 space-y-1.5">
                    {result.evaluation.notes.map((n) => (
                      <li key={n} className="text-xs text-accent-yellow/90">
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
                      navigate(`/decide/${encodeURIComponent(ticker.trim().toUpperCase())}`, {
                        state: {
                          conviction: result.conviction,
                          stance: result.stance,
                          thesis: result.analysis,
                          run_uid: result.run_uid,
                        },
                      })
                    }
                    className="bg-verdigris px-5 py-2.5 font-display text-label uppercase tracking-[0.14em] text-ink transition-colors hover:bg-cadmium"
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
                  <p className="mb-3 text-xs leading-relaxed text-gray-500">
                    The model's value was discarded in favour of the computed one.
                  </p>
                  {overrides.map((o) => (
                    <div key={o.field} className="flex flex-wrap items-baseline gap-2 text-sm">
                      <span className="font-mono text-gray-400">{o.field}</span>
                      <span className="font-mono text-gray-600 line-through">
                        {formatValue(o.model_said)}
                      </span>
                      <span className="text-gray-600">→</span>
                      <span className="font-mono text-accent-green">
                        {formatValue(o.harness_used)}
                      </span>
                      <span className="text-xs text-gray-600">from {o.source}</span>
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
                  <p className="mb-4 text-xs leading-relaxed text-gray-500">
                    These were answered with the recommended default. Choosing differently
                    re-runs the plan.
                  </p>
                  <div className="space-y-5">
                    {pending.map((c) => (
                      <div key={c.id}>
                        <p className="text-sm text-gray-300">{c.question}</p>
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
                                    ? "border-accent-blue/40 bg-accent-blue/10 text-accent-blue"
                                    : "border-border bg-surface text-gray-400 hover:border-border-light hover:text-gray-200"
                                }`}
                              >
                                {opt}
                                {opt === c.recommended && (
                                  <span className="ml-1.5 text-label uppercase tracking-wide text-gray-600">
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
                <p className="mt-2.5 font-mono text-label text-gray-700">
                  plan {exec.plan_hash.slice(0, 12)} · snapshot {exec.snapshot_sha256.slice(0, 12)}
                </p>
              </section>
            )}

            {/* Claims */}
            {verification && verification.claims.length > 0 && (
              <section>
                <SectionHeading hint={`${verification.unverifiable} unverifiable`}>
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
                  <p className="text-sm text-gray-400">
                    Resolved from{" "}
                    <span className="font-mono text-gray-300">
                      {result.data_quality.providers_used.join(", ") || "no provider"}
                    </span>
                  </p>
                  {result.data_quality.warning_count > 0 ? (
                    <ul className="mt-3 space-y-1.5">
                      {result.data_quality.warnings.map((w) => (
                        <li key={w} className="text-xs text-accent-yellow/90">
                          {w}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-2 text-xs text-gray-600">
                      No data-quality warnings on this snapshot.
                    </p>
                  )}
                </Card>
              </section>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
