import { useState } from "react";
import { InfoTip } from "./InfoTip";
import { useQuery } from "@tanstack/react-query";
import { api, type ConcentrationView } from "@/lib/api";

/**
 * Stage 06 — how big the view may be, and whether the book already agrees.
 *
 * Damodaran's point, and the reason this is separate from the sizing panel
 * next door: a diversified portfolio is an admission that you do not have
 * conviction. That is not a criticism — it is the correct response to not
 * having one. What is incoherent is claiming high conviction and holding
 * forty names, or holding six on a thesis whose weakest leg is unanswered.
 *
 * So it runs in both directions, and the second one is the reason to look.
 * Forwards it turns a conviction score into the largest position it justifies.
 * Backwards it takes the book you actually hold and reports the conviction
 * each position is implicitly claiming — because a position is a statement
 * about conviction whether or not anyone wrote the statement down.
 *
 * The score is typed in rather than recomputed. The conviction chain needs
 * answers to two judgment questions, and quietly re-deriving it here with
 * defaults would produce a size from a thesis nobody stated.
 */

function Row({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-md border-b border-ink-line py-xs last:border-b-0">
      <p className="text-body-sm text-on-ink-soft">{label}</p>
      <p className={`font-display text-mark tabular ${tone ?? "text-bone"}`}>
        {value}
      </p>
    </div>
  );
}

export function ConcentrationPanel({ ticker }: { ticker: string }) {
  const [score, setScore] = useState("");
  const [applied, setApplied] = useState<number | null>(null);
  // Typing "abc" used to clear the result with no explanation, because the
  // handler quietly resolved an unparseable value to null. A rejected input
  // has to say it was rejected.
  const [invalid, setInvalid] = useState(false);

  const q = useQuery({
    queryKey: ["concentration", ticker, applied],
    queryFn: () => api.getConcentration(ticker, applied ?? undefined),
    enabled: Boolean(ticker),
  });

  const d: ConcentrationView | undefined = q.data;

  return (
    <section
      className="flex flex-col gap-md"
      aria-label={`Concentration for ${ticker}`}
    >
      <div>
        <h2 className="flex items-center gap-xs font-display text-label uppercase tracking-label text-on-ink-faint">
          How big, and does the book agree?
          <InfoTip term="position-size" />
        </h2>
        <p className="mt-2xs max-w-measure text-body-sm text-on-ink-soft">
          A diversified book is an admission that you do not have conviction —
          which is the right answer when you do not. What does not hold together
          is claiming conviction and not sizing for it, or sizing for it without
          having claimed it.
        </p>
      </div>

      <form
        className="flex flex-wrap items-end gap-sm"
        onSubmit={(e) => {
          e.preventDefault();
          const raw = score.trim();
          const n = Number(raw);
          const ok = raw !== "" && Number.isFinite(n) && n >= 0 && n <= 1;
          setInvalid(raw !== "" && !ok);
          setApplied(ok ? n : null);
        }}
      >
        <label className="flex flex-col gap-2xs">
          <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
            Conviction (0–1) <InfoTip term="conviction" />
          </span>
          <input
            value={score}
            onChange={(e) => setScore(e.target.value)}
            inputMode="decimal"
            placeholder="0.35"
            aria-label="Conviction score from the chain in stage 05"
            aria-invalid={invalid}
            aria-describedby="conviction-hint"
            className={`w-[120px] border bg-ink px-sm py-1.5 font-display text-label text-bone outline-none transition-colors placeholder:text-on-ink-faint focus:border-cobalt ${
              invalid ? "border-oxide" : "border-ink-line"
            }`}
          />
          <span
            id="conviction-hint"
            className={`font-display text-label ${invalid ? "text-cadmium" : "text-on-ink-faint"}`}
          >
            {invalid
              ? "Needs a number between 0 and 1."
              : "From the chain in stage 05."}
          </span>
        </label>
        <button
          type="submit"
          className="border border-ink-line px-sm py-1.5 font-display text-label uppercase tracking-label text-bone transition-colors hover:border-cadmium hover:text-cadmium focus-visible:border-cadmium focus-visible:outline-none"
        >
          Size it
        </button>
      </form>

      {q.isLoading && (
        <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
          Pricing the book…
        </p>
      )}

      {q.error && (
        <div className="border border-oxide bg-ink-raised p-md shadow-elev-1">
          <p className="font-display text-label uppercase tracking-label text-cadmium">
            Could not size it
          </p>
          <p className="mt-xs max-w-measure text-body-sm text-on-ink-soft">
            {q.error instanceof Error ? q.error.message : "unknown error"}
          </p>
          <button
            type="button"
            onClick={() => void q.refetch()}
            disabled={q.isFetching}
            className="mt-sm border border-ink-line px-sm py-1.5 font-display text-label uppercase tracking-label text-bone transition-colors hover:border-cadmium hover:text-cadmium focus-visible:border-cadmium focus-visible:outline-none disabled:opacity-50"
          >
            {q.isFetching ? "Retrying…" : "Try again"}
          </button>
        </div>
      )}

      {d && !d.available && (
        <div className="border border-dashed border-ink-line bg-ink-raised p-md shadow-elev-1">
          <p className="font-display text-label uppercase tracking-label text-cadmium">
            No size yet
          </p>
          <p className="mt-xs max-w-measure text-body-sm text-on-ink-soft">
            {d.reason}
          </p>
          {(d.open_questions ?? []).map((question) => (
            <p
              key={question}
              className="mt-2xs max-w-measure text-body-xs text-on-ink-faint"
            >
              {question}
            </p>
          ))}
        </div>
      )}

      {d?.available && d.band && (
        <div className="border border-ink-line bg-ink-raised p-md shadow-elev-1">
          <Row
            label="Largest position this conviction justifies"
            value={`${d.band.max_weight_pct}%`}
            tone="text-cadmium"
          />
          <Row
            label="Which implies a book of about"
            value={`${d.band.implied_names} names`}
          />
          <p className="mt-sm max-w-measure text-body-sm text-on-ink-soft">
            {d.band.because}
          </p>
          <p className="mt-xs max-w-measure text-body-xs text-on-ink-faint">
            {d.band.implied_names_note}
          </p>
          {/* Repeated from the chain on purpose: the weakest leg decides HOW
              the view may be expressed and the band decides HOW MUCH. Showing
              the size alone invites putting the full weight into the one
              instrument the chain just ruled out. */}
          {d.structure?.allowed && (
            <p className="mt-sm border-t border-ink-line pt-sm text-body-sm text-on-ink-soft">
              And the weakest leg still says:{" "}
              <span className="text-cadmium">{d.structure.allowed}</span>
            </p>
          )}
        </div>
      )}

      {d?.book && (
        <div>
          <h3 className="flex items-center gap-xs font-display text-label uppercase tracking-label text-verdigris">
            What your book already claims
            <InfoTip term="implied-conviction" />
          </h3>
          <p className="mt-2xs max-w-measure text-body-sm text-on-ink-soft">
            {d.book.finding}
          </p>
          <ul className="mt-sm">
            {d.book.rows.map((r) => (
              /* A grid, not `justify-between`: three flex children space
                 themselves by their own widths, so a shorter verdict pulled
                 the percentage to a different x on every row and the column
                 stopped reading as a column. Fixed tracks keep the numbers
                 aligned down the page. */
              <li
                key={r.ticker}
                className="grid grid-cols-[1fr_auto] items-baseline gap-x-md gap-y-2xs border-b border-ink-line py-xs last:border-b-0 sm:grid-cols-[8rem_5rem_1fr]"
              >
                <span className="font-display text-mark text-bone">
                  {r.ticker}
                </span>
                <span className="font-display text-label tabular text-on-ink-soft sm:text-right">
                  {r.weight_pct.toFixed(1)}%
                </span>
                <span
                  className={`font-display text-label sm:text-right ${
                    r.overclaimed ? "text-oxide" : "text-on-ink-faint"
                  }`}
                >
                  {r.off_the_scale
                    ? "above the policy ceiling"
                    : `claims ≥ ${r.claims_at_least?.toFixed(2)}`}
                </span>
                {r.gap_note && (
                  <p className="col-span-full max-w-measure text-body-xs text-oxide">
                    {r.gap_note}
                  </p>
                )}
              </li>
            ))}
          </ul>

          {/* Never silently partial. A book comparison that has quietly dropped
              a third of the holdings is worse than none, because it looks
              complete. */}
          {d.book_excluded && d.book_excluded.length > 0 && (
            <p className="mt-sm max-w-measure text-body-xs text-on-ink-faint">
              Not counted: {d.book_excluded.join(", ")}. {d.book_excluded_note}
            </p>
          )}
        </div>
      )}

      {d?.book_note && (
        <p className="max-w-measure text-body-xs text-on-ink-faint">
          {d.book_note}
        </p>
      )}
    </section>
  );
}
