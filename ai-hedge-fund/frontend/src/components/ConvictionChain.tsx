import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type ConvictionLeg } from "@/lib/api";

/**
 * Conviction as three claims that must all hold, multiplied.
 *
 * Two of the three are judgments, so they are asked rather than derived —
 * there is no data feed for "what causes the correction". Only the margin of
 * safety arrives on its own, because the comparable range next door already
 * knows the gap.
 *
 * The legs are shown with the multiplication signs between them on purpose. A
 * reader who sees 0.0 x 0.7 x 1.0 understands immediately why a good catalyst
 * and a long horizon did not rescue the total, which is the one thing an
 * averaged score can never show.
 */

const EDGE_LABELS: Record<string, string> = {
  private_information: "Private information",
  information_processing: "Better processing of public information",
  business_understanding: "I understand this business better",
  pricing_mistake: "An identified pricing mistake",
};

function LegCard({ leg }: { leg: ConvictionLeg }) {
  const score = leg.score;
  const open = score === null;
  return (
    <div
      className={`flex-1 border p-sm ${
        open ? "border-dashed border-cadmium" : "border-ink-line bg-ink-raised"
      }`}
    >
      <p className="font-display text-label uppercase tracking-label text-on-ink-soft">
        {leg.label}
      </p>
      <p className="mt-2xs text-body-xs text-on-ink-faint">{leg.claim}</p>
      {open ? (
        <p className="mt-xs text-body-xs text-cadmium">Unanswered</p>
      ) : (
        <>
          <p className="mt-xs font-display text-mark text-bone tabular">
            {score.toFixed(2)}
          </p>
          <div className="mt-2xs h-1 rounded bg-ink" aria-hidden>
            <div
              className={`h-full rounded ${score < 0.3 ? "bg-oxide" : "bg-cobalt"}`}
              style={{ width: `${Math.max(score * 100, 1)}%` }}
            />
          </div>
        </>
      )}
    </div>
  );
}

export function ConvictionChain({ ticker }: { ticker: string }) {
  const [form, setForm] = useState({
    edge_source: "",
    catalyst: "",
    catalyst_certainty: "",
    days_to_catalyst: "",
    holding_period_days: "",
    recent_wins: "",
  });
  const [applied, setApplied] = useState(form);

  const q = useQuery({
    queryKey: ["conviction", ticker, applied],
    queryFn: () => api.getConviction(ticker, applied),
    enabled: Boolean(ticker),
  });

  const set = (k: keyof typeof form) => (v: string) =>
    setForm((f) => ({ ...f, [k]: v }));
  const d = q.data;

  const input =
    "border border-ink-line bg-ink px-sm py-1.5 font-display text-label text-bone outline-none transition-colors placeholder:text-on-ink-faint focus:border-cobalt";

  return (
    <section
      className="flex flex-col gap-md"
      aria-label={`Conviction for ${ticker}`}
    >
      <div className="flex flex-col gap-2xs">
        <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
          Conviction · three claims, multiplied
        </span>
        <p className="max-w-[72ch] text-body-xs text-on-ink-faint">
          Your price is right, and the market corrects, and it corrects while
          you can still be holding. One weak link caps the result, which is the
          point of multiplying rather than averaging.
        </p>
      </div>

      <form
        className="grid gap-sm sm:grid-cols-2 lg:grid-cols-3"
        onSubmit={(e) => {
          e.preventDefault();
          setApplied(form);
        }}
      >
        <label className="flex flex-col gap-2xs">
          <span className="font-display text-label uppercase tracking-label text-on-ink-soft">
            Where is the edge?
          </span>
          <select
            value={form.edge_source}
            onChange={(e) => set("edge_source")(e.target.value)}
            className={input}
          >
            <option value="">— name one —</option>
            {Object.entries(EDGE_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-2xs">
          <span className="font-display text-label uppercase tracking-label text-on-ink-soft">
            What causes the correction?
          </span>
          <input
            value={form.catalyst}
            onChange={(e) => set("catalyst")(e.target.value)}
            placeholder="Q1 earnings, a spin-off…"
            className={input}
          />
        </label>

        <label className="flex flex-col gap-2xs">
          <span className="font-display text-label uppercase tracking-label text-on-ink-soft">
            How certain is it? (0–1)
          </span>
          <input
            value={form.catalyst_certainty}
            onChange={(e) => set("catalyst_certainty")(e.target.value)}
            inputMode="decimal"
            placeholder="0.7"
            className={input}
          />
        </label>

        <label className="flex flex-col gap-2xs">
          <span className="font-display text-label uppercase tracking-label text-on-ink-soft">
            How long until it? (days)
          </span>
          <input
            value={form.days_to_catalyst}
            onChange={(e) => set("days_to_catalyst")(e.target.value)}
            inputMode="numeric"
            placeholder="120"
            className={input}
          />
        </label>

        <label className="flex flex-col gap-2xs">
          <span className="font-display text-label uppercase tracking-label text-on-ink-soft">
            How long can you hold? (days)
          </span>
          <input
            value={form.holding_period_days}
            onChange={(e) => set("holding_period_days")(e.target.value)}
            inputMode="numeric"
            placeholder="730"
            className={input}
          />
        </label>

        <label className="flex flex-col gap-2xs">
          <span className="font-display text-label uppercase tracking-label text-on-ink-soft">
            Wins in a row lately
          </span>
          <input
            value={form.recent_wins}
            onChange={(e) => set("recent_wins")(e.target.value)}
            inputMode="numeric"
            placeholder="0"
            className={input}
          />
          <span className="text-body-xs text-on-ink-faint">
            A streak raises confidence without adding evidence, so it takes a
            haircut.
          </span>
        </label>

        <div className="flex items-end">
          <button
            type="submit"
            className="border border-ink-line px-sm py-1.5 font-display text-label uppercase tracking-label text-on-ink-soft transition-colors hover:border-cobalt hover:text-bone"
          >
            Score it
          </button>
        </div>
      </form>

      {q.isLoading && (
        <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
          Scoring…
        </p>
      )}

      {d && (
        <>
          <div className="flex flex-wrap items-stretch gap-xs">
            {d.legs.map((leg, i) => (
              <div key={leg.key} className="flex flex-1 items-center gap-xs">
                <LegCard leg={leg} />
                {i < d.legs.length - 1 && (
                  <span
                    aria-hidden
                    className="font-display text-mark text-on-ink-faint"
                  >
                    ×
                  </span>
                )}
              </div>
            ))}
          </div>

          {d.margin_of_safety.value_pct !== null && (
            <p className="font-display text-label text-on-ink-faint tabular">
              Margin of safety {d.margin_of_safety.value_pct.toFixed(1)}% ·{" "}
              {d.margin_of_safety.source}
            </p>
          )}

          {!d.available ? (
            <div className="flex flex-col gap-2xs border-l-2 border-cadmium pl-sm">
              <p className="text-body-sm text-on-ink-soft">{d.reason}.</p>
              <ul className="flex flex-col gap-2xs">
                {d.open_questions.map((qq) => (
                  <li key={qq} className="text-body-xs text-cadmium">
                    {qq}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="flex flex-col gap-xs">
              <p className="text-body-sm text-on-ink-soft">
                Conviction{" "}
                <span className="tabular text-bone">
                  {(d.score * 100).toFixed(0)}%
                </span>{" "}
                — {d.label}. Weakest link:{" "}
                <span className="text-on-ink">{d.weakest_leg}</span>.
              </p>
              <div className="border border-ink-line bg-ink-raised p-sm">
                <p className="font-display text-label uppercase tracking-label text-cobalt">
                  What this allows
                </p>
                <p className="mt-2xs text-body-sm text-on-ink">
                  {d.structure.allowed}
                </p>
                <p className="mt-2xs max-w-[72ch] text-body-xs text-on-ink-faint">
                  {d.structure.because}
                </p>
              </div>
              {d.humility.haircut > 0 && (
                <p className="max-w-[72ch] text-body-xs text-oxide">
                  {d.humility.note}
                </p>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
