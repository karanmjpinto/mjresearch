import type { ExperimentRow } from "@/lib/api";

/**
 * What every experiment did once it left the data it was fitted on.
 *
 * The autoresearch page was a wall of figures — Sharpe, Sortino, drawdown,
 * win rate, time in market, twice each for two windows, for eight experiments.
 * Every number was correct and the finding was invisible.
 *
 * There is exactly one finding, and it is a shape: the searcher only ever sees
 * the in-sample window, the out-of-sample window decides, and almost every
 * rule is worse once it gets there. Drawn as a line per experiment from where
 * it was fitted to where it was tested, that decay is the first thing you see
 * and it needs no explaining.
 *
 * The baseline gets a vertical rule, because "better than nothing" is not the
 * test — buy-and-hold is, and a rule landing left of that line has lost to
 * doing nothing at all after fees.
 *
 * Deliberately one metric. Showing six would restore the wall this replaces,
 * and the harness already nominates the one that decides the verdict.
 */

/* The app's own row type rather than a local restatement of it. A private
 * shape here would drift from the API the first time a field is renamed, and
 * the chart would go quietly blank. */
type Props = {
  experiments: ExperimentRow[];
  /** Name of the metric being drawn, for the axis label. */
  metric?: string;
};

const ROW = 28;
const PAD = { top: 28, right: 18, bottom: 36, left: 150 };

/**
 * Type size for everything drawn inside the SVG.
 *
 * Twelve, matching `fontSize.label` in tailwind.config.ts, and the SVG is
 * rendered at its intrinsic size so these units are real pixels. Scaling the
 * drawing to its container instead — `w-full` on a 720-wide viewBox — silently
 * scales the type with it, and at phone width these labels landed near 7px.
 * The wrapper scrolls sideways rather than shrinking the words.
 */
const LABEL_PX = 12;

/**
 * Width reserved on the right for the verdict word.
 *
 * The plot used to run the full width and the verdict was right-anchored on
 * top of it, so any experiment scoring near the top of the scale put its
 * marker straight through the word "discarded". Giving the column its own
 * space costs a little range and removes the collision entirely.
 */
const VERDICT_W = 88;

const num = (v: number | null | undefined): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;

export function DecayChart({ experiments, metric = "Sharpe ratio" }: Props) {
  const rows = experiments
    .map((e) => ({
      label: (e.strategy_id ?? "—").replace(/_/g, " "),
      verdict: e.is_baseline ? "baseline" : (e.verdict ?? "—"),
      hypothesis: e.hypothesis,
      inSample: num(e.in_sample?.sharpe_ratio),
      outSample: num(e.out_of_sample?.sharpe_ratio),
    }))
    .filter((r) => r.inSample != null || r.outSample != null);

  if (rows.length === 0) return null;

  /* The baseline's out-of-sample score is the bar every rule has to clear —
   * but only when there is one of them. The leaderboard spans runs and
   * tickers, so a set can contain several baselines at different levels, and
   * drawing the first as *the* reference would invite comparing a rule tested
   * on one name against buy-and-hold on another. Where they disagree, no line
   * is drawn and the caption says why. */
  const baselines = rows
    .filter((r) => r.verdict === "baseline")
    .map((r) => r.outSample)
    .filter((v): v is number => v != null);
  const oneBaseline =
    baselines.length > 0 && Math.max(...baselines) - Math.min(...baselines) < 0.02;
  const baseline = oneBaseline ? baselines[0]! : null;

  const values = rows.flatMap((r) => [r.inSample, r.outSample]).filter((v): v is number => v != null);
  const lo = Math.min(0, ...values);
  const hi = Math.max(...values, baseline ?? 0) * 1.08;
  const span = hi - lo || 1;

  const H = PAD.top + rows.length * ROW + PAD.bottom;
  const W = 720;
  const plotW = W - PAD.left - PAD.right - VERDICT_W;
  const plotRight = PAD.left + plotW;
  const x = (v: number) => PAD.left + ((v - lo) / span) * plotW;
  const y = (i: number) => PAD.top + i * ROW + ROW / 2;

  const tone = (v: string) =>
    v === "kept" ? "var(--verdigris)" : v === "baseline" ? "var(--cobalt)" : "var(--oxide)";

  const kept = rows.filter((r) => r.verdict === "kept").length;
  const tested = rows.filter((r) => r.verdict !== "baseline").length;

  return (
    <figure className="m-0 flex flex-col gap-xs">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`${metric} for ${tested} experiments, fitted then tested out of sample. ${kept} kept.`}
          width={W}
          height={H}
          className="block max-w-none text-on-ink-faint"
        >
          {/* The baseline. Drawn first so every line crosses over it. */}
          {baseline != null && (
            <>
              <line
                x1={x(baseline)}
                x2={x(baseline)}
                y1={PAD.top - 12}
                y2={PAD.top + rows.length * ROW}
                stroke="var(--cobalt)"
                strokeWidth={1.5}
                strokeDasharray="4 3"
              />
              <text
                x={x(baseline)}
                y={PAD.top - 16}
                textAnchor="middle"
                fontSize={LABEL_PX}
                fill="var(--cobalt)"
              >
                buy and hold {baseline.toFixed(2)}
              </text>
            </>
          )}

          {rows.map((r, i) => {
            const yy = y(i);
            const a = r.inSample;
            const b = r.outSample;
            const c = tone(r.verdict);
            return (
              <g key={`${r.label}-${i}`}>
                <text
                  x={PAD.left - 10}
                  y={yy + 3}
                  textAnchor="end"
                  fontSize={LABEL_PX}
                  fill="currentColor"
                >
                  {r.label}
                </text>

                {/* The decay itself: fitted at the hollow end, tested at the
                  * solid one. Direction carries the whole story. */}
                {a != null && b != null && (
                  <line
                    x1={x(a)}
                    x2={x(b)}
                    y1={yy}
                    y2={yy}
                    stroke={c}
                    strokeWidth={1.5}
                    opacity={0.55}
                  />
                )}
                {a != null && (
                  <circle cx={x(a)} cy={yy} r={3.5} fill="none" stroke={c} strokeWidth={1.5} />
                )}
                {b != null && <circle cx={x(b)} cy={yy} r={4} fill={c} />}

                <text
                  x={W - PAD.right}
                  y={yy + 3}
                  textAnchor="end"
                  fontSize={LABEL_PX}
                  fill={c}
                >
                  {r.verdict}
                </text>
              </g>
            );
          })}

          {/* Axis: ends plus zero, so every label names a value on the scale. */}
          <line
            x1={PAD.left}
            x2={plotRight}
            y1={PAD.top + rows.length * ROW}
            y2={PAD.top + rows.length * ROW}
            stroke="currentColor"
          />
          <text x={PAD.left} y={H - 16} fontSize={LABEL_PX} fill="currentColor">
            {lo.toFixed(2)}
          </text>
          <text
            x={(PAD.left + plotRight) / 2}
            y={H - 16}
            textAnchor="middle"
            fontSize={LABEL_PX}
            fill="currentColor"
          >
            {metric} — hollow: fitted · solid: tested out of sample
          </text>
          <text x={plotRight} y={H - 16} textAnchor="end" fontSize={LABEL_PX} fill="currentColor">
            {hi.toFixed(2)}
          </text>
        </svg>
      </div>
      <figcaption className="max-w-measure text-body-xs text-on-ink-faint">
        Each line runs from where a rule was fitted to where it was tested.
        Leftward is decay — the rule was partly fitting noise.
        {baseline != null ? (
          <>
            {" "}A rule landing left of the dashed line lost to buy-and-hold
            after fees, which is the bar that matters.
          </>
        ) : baselines.length > 1 ? (
          <>
            {" "}These experiments span more than one run, and their
            buy-and-hold baselines differ, so no single reference line is drawn
            — compare each rule against the baseline from its own run in the
            log below.
          </>
        ) : null}
      </figcaption>
    </figure>
  );
}
