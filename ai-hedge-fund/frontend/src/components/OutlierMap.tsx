import { useMemo, useState } from "react";
import type { ScreenRow } from "@/lib/api";

/**
 * Every name in a screen, plotted — so the outliers are visible as outliers
 * rather than as the top of a sorted list.
 *
 * A ranked table answers "what scored highest". It cannot answer "is the top
 * name genuinely apart from the field, or a rounding error above the second",
 * and those call for different sizes. The whole field has to be on screen for
 * that, including the names that failed, which is why this plots the full run
 * rather than the passing rows.
 *
 * FOUR ENCODINGS, each doing a job it is suited to:
 *
 *   x, y    two chosen measures. Default to the pair that is this desk's
 *           actual thesis — return on capital already deployed against the
 *           rate it can compound at unaided. Akre's stool is a scatter plot
 *           nobody had drawn.
 *   area    market cap, on a square-root scale so area and not radius carries
 *           the value. Radius-scaled bubbles overstate large values by the
 *           square, which is the oldest bug in this chart type.
 *   colour  the screen's own score, as a sequential ramp. Score is a
 *           magnitude, so it gets one hue light to dark — never a set of
 *           categorical hues, which would imply the scores are identities.
 *
 * The find is the top right, large and dark: high return, long runway, real
 * size, and the screen agrees. A name that is top-right and *pale* is the
 * interesting disagreement — the two measures like it and the other eight
 * factors do not.
 */

type Axis = { key: string; label: string; pct: boolean };

/** Fields worth putting on an axis, with how they should read. */
const AXES: readonly Axis[] = [
  { key: "roic", label: "Return on capital", pct: true },
  { key: "implied_compounding", label: "Implied compounding", pct: true },
  { key: "reinvestment_rate", label: "Reinvestment rate", pct: true },
  { key: "roiic", label: "Return on incremental capital", pct: true },
  { key: "fcf_conversion", label: "FCF conversion", pct: true },
  { key: "revenue_cagr_5y", label: "Revenue CAGR 5y", pct: true },
  { key: "net_debt_to_ebitda", label: "Net debt / EBITDA", pct: false },
  { key: "interest_coverage", label: "Interest coverage", pct: false },
  { key: "share_cagr_5y", label: "Share count CAGR 5y", pct: true },
] as const;

const SEQ = ["var(--seq-1)", "var(--seq-2)", "var(--seq-3)", "var(--seq-4)", "var(--seq-5)"];

type Point = {
  ticker: string;
  x: number;
  y: number;
  cap: number | null;
  score: number | null;
  passed: boolean;
};

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function fmt(v: number, pct: boolean): string {
  if (pct) return `${(v * 100).toFixed(0)}%`;
  if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(1)}bn`;
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(0)}m`;
  return v.toFixed(1);
}

/** The value at a percentile of a sorted array, interpolated. */
function quantile(sorted: readonly number[], q: number): number {
  if (sorted.length === 0) return 0;
  const i = (sorted.length - 1) * q;
  const lo = Math.floor(i);
  const hi = Math.ceil(i);
  return lo === hi ? sorted[lo]! : sorted[lo]! + (sorted[hi]! - sorted[lo]!) * (i - lo);
}

/** Ticks that land on round numbers rather than on the data's extremes. */
function ticks(lo: number, hi: number, count = 4): number[] {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? mag * 10;
  const out: number[] = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) out.push(t);
  return out;
}

export function OutlierMap({
  rows,
  caption,
}: {
  rows: readonly ScreenRow[];
  caption?: string;
}) {
  const [xKey, setXKey] = useState("roic");
  const [yKey, setYKey] = useState("implied_compounding");
  const [showTable, setShowTable] = useState(false);
  const [hover, setHover] = useState<Point | null>(null);

  const xAxis = AXES.find((a) => a.key === xKey)!;
  const yAxis = AXES.find((a) => a.key === yKey)!;

  const points = useMemo<Point[]>(() => {
    const out: Point[] = [];
    for (const r of rows) {
      const snap = (r.snapshot ?? {}) as Record<string, unknown>;
      const x = num(snap[xKey]);
      const y = num(snap[yKey]);
      if (x === null || y === null) continue; // a missing measure is not a zero
      out.push({
        ticker: String(r.ticker ?? "?"),
        x,
        y,
        cap: num(snap.market_cap),
        score: num(r.total_score) ?? num((r.scores as { total?: number })?.total),
        passed: r.stage1_passed === true,
      });
    }
    return out;
  }, [rows, xKey, yKey]);

  const W = 720;
  const H = 420;
  const M = { t: 16, r: 16, b: 46, l: 58 };

  const geom = useMemo(() => {
    if (points.length === 0) return null;
    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    /* Clipped to p2-p98, not to the extremes, and this is the difference
     * between a chart and a smear.
     *
     * These measures are ratios with a denominator that can approach zero, so
     * the tail is not a long tail — it is a different order of magnitude. On
     * the S&P 400 run the median return on capital is 9.9% and the maximum is
     * 853%, because a company that has bought back enough stock has almost no
     * invested capital left to divide by. Three names at 853%, 837% and 193%
     * put the other 226 in a blob four pixels wide.
     *
     * Dropping them would be worse than the smear: those three are the most
     * interesting rows on the screen, and what they are telling you is that
     * the denominator broke, not that the business earns eight times its
     * capital. So the scale is robust, the outliers are pinned to the edge
     * with a ring that says "beyond this", and the caption names them. The
     * reader is told what was clipped rather than shown a tidy chart that
     * quietly dropped it. */
    const pad = (lo: number, hi: number) => {
      const d = (hi - lo) || Math.abs(hi) || 1;
      return [lo - d * 0.08, hi + d * 0.08] as const;
    };
    const sx = [...xs].sort((a, b) => a - b);
    const sy = [...ys].sort((a, b) => a - b);
    const [x0, x1] = pad(quantile(sx, 0.02), quantile(sx, 0.98));
    const [y0, y1] = pad(quantile(sy, 0.02), quantile(sy, 0.98));
    const caps = points.map((p) => p.cap ?? 0);
    const capMax = Math.max(...caps, 1);
    const scores = points.map((p) => p.score ?? 0);
    const sMin = Math.min(...scores);
    const sMax = Math.max(...scores, sMin + 1);

    const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
    const px = (v: number) =>
      M.l + ((clamp(v, x0, x1) - x0) / (x1 - x0)) * (W - M.l - M.r);
    const py = (v: number) =>
      H - M.b - ((clamp(v, y0, y1) - y0) / (y1 - y0)) * (H - M.t - M.b);
    const off = (p: Point) => p.x < x0 || p.x > x1 || p.y < y0 || p.y > y1;
    // sqrt so AREA carries market cap, floored at 4px so the smallest name
    // is still a target you can hit.
    const pr = (c: number | null) => 4 + Math.sqrt((c ?? 0) / capMax) * 14;
    const pc = (s: number | null) =>
      s === null
        ? "var(--seq-2)"
        : SEQ[Math.min(SEQ.length - 1, Math.floor(((s - sMin) / (sMax - sMin)) * SEQ.length))]!;

    return { x0, x1, y0, y1, px, py, pr, pc, off, sMin, sMax, capMax };
  }, [points]);

  if (!geom || points.length === 0) {
    return (
      <p className="text-sm text-on-ink-faint">
        No plottable rows — this run has no values for those two measures.
      </p>
    );
  }

  /* Labelled selectively, never on every point: the names worth reading are
   * the ones furthest from the middle of the field, and a label on all of
   * them is a wall of text with a chart behind it. */
  const clipped = points.filter((p) => geom.off(p));

  const labelled = new Set(
    [...points]
      .sort(
        (a, b) =>
          (b.x - geom.x0) / (geom.x1 - geom.x0) +
          (b.y - geom.y0) / (geom.y1 - geom.y0) -
          ((a.x - geom.x0) / (geom.x1 - geom.x0) + (a.y - geom.y0) / (geom.y1 - geom.y0)),
      )
      .slice(0, 6)
      .map((p) => p.ticker),
  );

  return (
    <figure className="m-0">
      <div className="mb-sm flex flex-wrap items-end gap-md">
        {[
          { v: xKey, set: setXKey, id: "x-measure", label: "Across" },
          { v: yKey, set: setYKey, id: "y-measure", label: "Up" },
        ].map((sel) => (
          <div key={sel.id} className="flex flex-col gap-2xs">
            <label
              htmlFor={sel.id}
              className="font-display text-label uppercase tracking-marker text-on-ink-faint"
            >
              {sel.label}
            </label>
            <select
              id={sel.id}
              value={sel.v}
              onChange={(e) => sel.set(e.target.value)}
              className="border border-ink-line bg-ink px-sm py-1.5 font-display text-label tracking-label text-bone outline-none transition-colors focus:border-cobalt"
            >
              {AXES.map((a) => (
                <option key={a.key} value={a.key}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>
        ))}
        <p className="text-sm text-on-ink-faint">
          <span className="tabular text-on-ink-soft">{points.length}</span> names
          plotted · area is market cap · colour is the screen&apos;s score
        </p>
      </div>

      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full min-w-[560px]"
          role="img"
          aria-label={`${yAxis.label} against ${xAxis.label} for ${points.length} names. The table below carries the same figures.`}
        >
          {/* Recessive grid — it locates a mark and must never compete with one. */}
          {ticks(geom.y0, geom.y1).map((t) => (
            <g key={`y${t}`}>
              <line
                x1={M.l}
                x2={W - M.r}
                y1={geom.py(t)}
                y2={geom.py(t)}
                stroke="var(--ink-line)"
                strokeWidth="1"
              />
              <text
                x={M.l - 8}
                y={geom.py(t) + 4}
                textAnchor="end"
                className="fill-on-ink-faint font-display"
                style={{ fontSize: 11 }}
              >
                {fmt(t, yAxis.pct)}
              </text>
            </g>
          ))}
          {ticks(geom.x0, geom.x1).map((t) => (
            <g key={`x${t}`}>
              <line
                x1={geom.px(t)}
                x2={geom.px(t)}
                y1={M.t}
                y2={H - M.b}
                stroke="var(--ink-line)"
                strokeWidth="1"
              />
              <text
                x={geom.px(t)}
                y={H - M.b + 18}
                textAnchor="middle"
                className="fill-on-ink-faint font-display"
                style={{ fontSize: 11 }}
              >
                {fmt(t, xAxis.pct)}
              </text>
            </g>
          ))}

          <text
            x={(W - M.l) / 2 + M.l}
            y={H - 6}
            textAnchor="middle"
            className="fill-on-ink-soft font-display"
            style={{ fontSize: 11 }}
          >
            {xAxis.label} →
          </text>
          <text
            x={-((H - M.b) / 2)}
            y={14}
            transform="rotate(-90)"
            textAnchor="middle"
            className="fill-on-ink-soft font-display"
            style={{ fontSize: 11 }}
          >
            {yAxis.label} →
          </text>

          {/* Largest first, so a small name is never buried under a big one. */}
          {[...points]
            .sort((a, b) => (b.cap ?? 0) - (a.cap ?? 0))
            .map((p) => (
              <circle
                key={p.ticker}
                cx={geom.px(p.x)}
                cy={geom.py(p.y)}
                r={geom.pr(p.cap)}
                fill={geom.pc(p.score)}
                /* A surface-coloured ring, so overlapping marks stay countable
                 * instead of merging into one blob. */
                /* A clipped mark gets the accent ring: it is sitting on the
                 * edge because its real value is off this scale, and without
                 * the ring it reads as a name that genuinely scored there. */
                stroke={geom.off(p) ? "var(--cadmium)" : "var(--ink)"}
                strokeWidth="2"
                opacity={p.passed ? 1 : 0.45}
                onMouseEnter={() => setHover(p)}
                onMouseLeave={() => setHover(null)}
              >
                <title>
                  {`${p.ticker} — ${xAxis.label} ${fmt(p.x, xAxis.pct)}, ${yAxis.label} ${fmt(p.y, yAxis.pct)}` +
                    (p.cap ? `, cap ${fmt(p.cap, false)}` : "") +
                    (p.score !== null ? `, score ${p.score}` : "") +
                    (geom.off(p) ? " — beyond the scale, pinned to the edge" : "") +
                    (p.passed ? "" : " — did not clear the hard filters")}
                </title>
              </circle>
            ))}

          {points
            .filter((p) => labelled.has(p.ticker))
            .map((p) => (
              <text
                key={`l${p.ticker}`}
                x={geom.px(p.x) + geom.pr(p.cap) + 4}
                y={geom.py(p.y) + 4}
                className="fill-bone font-display"
                style={{ fontSize: 11 }}
              >
                {p.ticker}
              </text>
            ))}
        </svg>
      </div>

      <figcaption className="mt-sm flex flex-wrap items-center gap-md">
        <span className="flex items-center gap-2xs">
          <span className="font-display text-label uppercase tracking-marker text-on-ink-faint">
            Score
          </span>
          {SEQ.map((c, i) => (
            <span
              key={c}
              aria-hidden="true"
              className="inline-block h-2 w-5"
              style={{ background: c }}
              title={i === 0 ? "lowest" : i === SEQ.length - 1 ? "highest" : undefined}
            />
          ))}
          <span className="tabular text-sm text-on-ink-faint">
            {Math.round(geom.sMin)}–{Math.round(geom.sMax)}
          </span>
        </span>
        <span className="text-sm text-on-ink-faint">
          Faded marks did not clear the hard filters — plotted anyway, because
          the field is the point.
        </span>
        {clipped.length > 0 && (
          <span className="text-sm text-on-ink-soft">
            <span className="text-cadmium">
              {clipped.length} beyond this scale
            </span>
            , pinned to the edge:{" "}
            {clipped
              .slice(0, 4)
              .map(
                (p) =>
                  `${p.ticker} ${p.x > geom.x1 || p.x < geom.x0 ? fmt(p.x, xAxis.pct) : fmt(p.y, yAxis.pct)}`,
              )
              .join(", ")}
            {clipped.length > 4 && ` and ${clipped.length - 4} more`}. A ratio
            that large is usually a denominator that collapsed, not a business
            that earns it.
          </span>
        )}
      </figcaption>

      {hover && (
        <p className="mt-xs font-display text-label tracking-label text-bone">
          {hover.ticker} · {xAxis.label} {fmt(hover.x, xAxis.pct)} ·{" "}
          {yAxis.label} {fmt(hover.y, yAxis.pct)}
          {hover.score !== null && ` · score ${hover.score}`}
        </p>
      )}

      <button
        type="button"
        onClick={() => setShowTable((v) => !v)}
        aria-expanded={showTable}
        className="mt-sm font-display text-label uppercase tracking-marker text-on-ink-faint underline underline-offset-2 transition-colors hover:text-bone"
      >
        {showTable ? "Hide the numbers" : "Read it as a table"}
      </button>

      {showTable && (
        <div className="mt-xs max-h-[320px] overflow-auto">
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 bg-ink">
              <tr>
                {["Ticker", xAxis.label, yAxis.label, "Market cap", "Score"].map((h) => (
                  <th
                    key={h}
                    scope="col"
                    className="border-b border-ink-line py-2xs pr-md text-left font-display text-label uppercase tracking-marker text-on-ink-faint"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...points]
                .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
                .map((p) => (
                  <tr key={p.ticker}>
                    <td className="border-b border-ink-line py-2xs pr-md text-bone">
                      {p.ticker}
                    </td>
                    <td className="tabular border-b border-ink-line py-2xs pr-md text-on-ink-soft">
                      {fmt(p.x, xAxis.pct)}
                    </td>
                    <td className="tabular border-b border-ink-line py-2xs pr-md text-on-ink-soft">
                      {fmt(p.y, yAxis.pct)}
                    </td>
                    <td className="tabular border-b border-ink-line py-2xs pr-md text-on-ink-soft">
                      {p.cap === null ? "—" : fmt(p.cap, false)}
                    </td>
                    <td className="tabular border-b border-ink-line py-2xs text-on-ink-soft">
                      {p.score ?? "—"}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      {caption && <p className="mt-xs text-sm text-on-ink-faint">{caption}</p>}
    </figure>
  );
}
