/**
 * The window this was computed over, drawn.
 *
 * The optimiser already returned its start date, end date and bar count, and
 * the screen printed them as one small grey line — `2024-09-16 → 2026-09-16 ·
 * 502 bars`. Everything needed to understand the result was present and
 * nothing about it registered.
 *
 * What was missing is not data, it is the frame. Every number on that page —
 * the expected return, the volatility, the correlations the weights come from
 * — is measured *backwards* over this window and nothing else. That is the
 * single most important caveat on the screen and it was the least visible
 * thing on it, which is how a backtest gets read as a forecast.
 *
 * So the window becomes a bar with both ends dated, the span named in years,
 * and one sentence saying which direction it looks. A reader who takes only
 * the picture still leaves knowing the answer came from the past.
 *
 * Drawn, not tabulated, because the span is the point: two years and ten years
 * are different claims, and a pair of dates makes you do the subtraction.
 */

type Props = {
  start: string | null | undefined;
  end: string | null | undefined;
  /** Trading days actually used, which is not the calendar span. */
  bars?: number | null;
  /** What was asked for, to show when the data could not supply it. */
  requestedDays?: number;
  /** What the window was used for, in the reader's words. */
  purpose?: string;
};

const MS_PER_YEAR = 365.25 * 24 * 3600 * 1000;

function parse(d: string | null | undefined): Date | null {
  if (!d) return null;
  const t = Date.parse(d);
  return Number.isNaN(t) ? null : new Date(t);
}

export function LookbackTimeline({
  start,
  end,
  bars,
  requestedDays,
  purpose = "Every figure below is measured over this window and nothing outside it.",
}: Props) {
  const from = parse(start);
  const to = parse(end);
  if (!from || !to || to <= from) return null;

  const years = (to.getTime() - from.getTime()) / MS_PER_YEAR;
  const span =
    years >= 1
      ? `${years.toFixed(years >= 10 ? 0 : 1)} years`
      : `${Math.round(years * 12)} months`;

  // What was asked for versus what arrived. A name that listed two years ago
  // silently shortens the window for the whole basket, and the old line gave
  // no way to notice.
  const requestedYears = requestedDays ? requestedDays / 365.25 : null;
  const short =
    requestedYears != null && years < requestedYears * 0.9
      ? `Asked for ${requestedYears.toFixed(1)} years; the shortest history in the basket allowed ${span}.`
      : null;

  return (
    <figure className="m-0 flex flex-col gap-xs">
      <div className="flex flex-wrap items-baseline justify-between gap-sm">
        <h3 className="font-display text-label uppercase tracking-label text-on-ink-faint">
          Measured over
        </h3>
        <p className="font-display text-mark tabular text-cadmium">
          {span} back
          {typeof bars === "number" && bars > 0 && (
            <span className="ml-sm text-on-ink-faint">{bars} trading days</span>
          )}
        </p>
      </div>

      {/* Drawn in HTML, not SVG.
        *
        * The first version put the dates and the direction label inside the
        * SVG at 11 units on a 720-wide viewBox scaled to the container. Those
        * units are not pixels: at phone width the whole drawing scales to
        * about half size and the dates rendered near 6px, well under the 12px
        * floor this design system sets. A label that only holds at desktop
        * width is not a label. The bar is three rectangles and a triangle, so
        * it costs nothing to draw in HTML and let the type keep its size. */}
      <p
        className="text-center font-display text-label uppercase tracking-label text-on-ink-faint"
        aria-hidden="true"
      >
        ← looking back {span}
      </p>

      <div
        role="img"
        aria-label={`Window from ${start} to ${end}, ${span}, looking backwards from today.`}
        className="relative h-2.5 w-full bg-cobalt/30"
      >
        {/* The far end of the window. */}
        <span className="absolute left-0 top-0 h-full w-[3px] bg-cobalt" />
        {/* Today, and an arrowhead pointing back the way the reader is
          * looking. It points left, not right — a rightward head would read
          * as "time flows this way" and contradict the label above it, which
          * is the confusion the arrow exists to remove. */}
        <span className="absolute right-0 top-[-4px] h-[18px] w-[3px] bg-cadmium" />
        <span
          className="absolute right-[7px] top-1/2 h-0 w-0 -translate-y-1/2 border-y-[6px] border-r-[12px] border-y-transparent border-r-cadmium"
        />
      </div>

      <div className="flex items-baseline justify-between gap-sm">
        <span className="font-display text-label tabular text-on-ink-faint">{start}</span>
        <span className="font-display text-label tabular text-cadmium">{end}</span>
      </div>

      <figcaption className="max-w-measure text-body-xs text-on-ink-faint">
        {purpose}
        {short && <span className="ml-xs text-cadmium">{short}</span>}
      </figcaption>
    </figure>
  );
}
