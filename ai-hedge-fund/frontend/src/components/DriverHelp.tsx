import type { DriverGuidanceEntry } from "@/lib/api";
import { Popover } from "./Popover";

/**
 * How to think about a number you have been asked to invent.
 *
 * A definition does not answer the question anyone actually has here. Being
 * told revenue growth is "how fast sales grow" leaves you exactly as unable to
 * decide between 6% and 18% as before. What settles it is a reference point,
 * and this panel carries the three that exist:
 *
 *   What the price implies  the rate today's price is already paying for,
 *                           solved backwards through the same model. This is
 *                           the useful one, because it turns a blank box into
 *                           a position — above it you are the optimist.
 *   The company's own       derived from the filings, with the derivation said
 *                           out loud rather than presented as a fact.
 *   The hard bound          where one exists. Terminal growth cannot exceed
 *                           the risk-free rate, and that is arithmetic, not
 *                           taste.
 *
 * Where a driver has none of the three — the chance of failure, which has no
 * vendored table here — the panel says the figure is a judgment instead of
 * dressing a guess as a reference. That admission is the point: a screen that
 * offered an authoritative-looking default for every box would be inviting
 * people to accept numbers nobody stands behind.
 */

const asPct = (v: number | null | undefined, dp = 1) =>
  typeof v === "number" ? `${(v * 100).toFixed(dp)}%` : null;
const asX = (v: number | null | undefined) =>
  typeof v === "number" ? `${v.toFixed(2)}x` : null;

/** Sales-to-capital is a multiple; everything else here is a rate. */
function format(key: string, v: number | null | undefined): string | null {
  return key === "sales_to_capital" ? asX(v) : asPct(v);
}

function Figure({
  label,
  value,
  tone,
  note,
}: {
  label: string;
  value: string;
  tone?: string;
  note?: string;
}) {
  return (
    <span className="flex flex-col gap-2xs border-l-2 border-ink-line pl-sm">
      <span className="block font-display text-label uppercase tracking-label text-on-ink-faint">
        {label}
      </span>
      <span
        className={`block font-display text-mark tabular ${tone ?? "text-bone"}`}
      >
        {value}
      </span>
      {note && (
        <span className="block text-body-xs text-on-ink-faint">{note}</span>
      )}
    </span>
  );
}

export function DriverHelp({ entry }: { entry: DriverGuidanceEntry }) {
  const implied = format(entry.key, entry.market_implied);
  const yours = format(entry.key, entry.yours);
  const ceiling = format(entry.key, entry.ceiling);

  return (
    <Popover label={`How should I choose ${entry.label}?`} width={26}>
      <span className="block font-display text-label uppercase tracking-label text-cadmium">
        {entry.label}
      </span>

      <span className="block text-body-xs leading-relaxed text-on-ink">
        {entry.what}
      </span>

      {/* The reference points, ahead of the prose: someone opening this
       * wants a number to aim at, not a paragraph first. */}
      {(implied || yours || ceiling) && (
        <span className="grid gap-sm border-t border-ink-line pt-sm sm:grid-cols-2">
          {implied && (
            <Figure
              label="What the price implies"
              value={implied}
              tone="text-cadmium"
              note="Above this you are more optimistic than the market."
            />
          )}
          {yours && (
            <Figure
              label="This company's own"
              value={yours}
              note="Derived from the filings."
            />
          )}
          {ceiling && (
            <Figure
              label="Hard ceiling"
              value={ceiling}
              tone="text-oxide"
              note={entry.ceiling_source}
            />
          )}
        </span>
      )}

      {entry.sourced === false && (
        <span className="block border-t border-ink-line pt-xs text-body-xs leading-relaxed text-cadmium">
          No reference table is vendored for this one, so there is no figure to
          aim at — it is a judgment, and it defaults to zero rather than to
          something that looks authoritative.
        </span>
      )}

      <span className="block border-t border-ink-line pt-xs text-body-xs leading-relaxed text-on-ink-soft">
        <span className="text-on-ink-faint">What moves it: </span>
        {entry.moves}
      </span>

      <span className="block text-body-xs leading-relaxed text-on-ink-soft">
        <span className="text-on-ink-faint">
          Where it stops being defensible:{" "}
        </span>
        {entry.bound}
      </span>
    </Popover>
  );
}
