import { useEffect, useRef, useState, type RefObject } from "react";
import type { FactorRow } from "@/lib/api";
import {
  fixed,
  legOf,
  monthLabel,
  signedPct,
  type Point,
} from "@/lib/factors";

/**
 * The drawings on the Factors tab. Hand-built SVG, like `DecayChart`, so every
 * colour is a palette token and every label is real 12px type: the SVGs are
 * drawn at the width they are shown at rather than scaled to fit, which is
 * what shrinks chart text below the legibility floor.
 *
 * Colour jobs, fixed across the tab:
 *   cobalt   the long side of a factor (where JKP buy)
 *   cadmium  the short side
 *   on-ink   the lines themselves — one series per chart, so the title names it
 *   verdigris / oxide   only for "held" / "did not hold" after publication, and
 *                       always next to the word.
 */

const LABEL_PX = 12;

/** Width of an element, tracked. Charts draw at this so type stays 12px. */
export function useWidth<T extends HTMLElement>(): [RefObject<T | null>, number] {
  const ref = useRef<T | null>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

// ── Tilt ───────────────────────────────────────────────────────────────────

/**
 * A company's position on one theme, 0–100, drawn from the median outwards.
 *
 * Diverging from 50 rather than filling from 0, because the question is which
 * side of the factor the company is on, and how far. Colour carries the side;
 * the number and the word beside it carry it too.
 */
export function TiltBar({ score, width = 132 }: { score: number; width?: number }) {
  const h = 12;
  const mid = width / 2;
  const x = (score / 100) * width;
  const leg = legOf(score);
  const fill =
    leg === "long" ? "var(--cobalt)" : leg === "short" ? "var(--cadmium)" : "var(--aluminium)";
  return (
    <svg
      width={width}
      height={h}
      aria-hidden="true"
      className="block shrink-0 text-ink-line"
    >
      <rect x={0} y={h / 2 - 1} width={width} height={2} fill="currentColor" />
      <rect
        x={Math.min(mid, x)}
        y={2}
        width={Math.max(2, Math.abs(x - mid))}
        height={h - 4}
        rx={2}
        fill={fill}
      />
      <line x1={mid} x2={mid} y1={0} y2={h} stroke="var(--on-ground-faint)" strokeWidth={1} />
    </svg>
  );
}

// ── Sparkline ──────────────────────────────────────────────────────────────

/**
 * Growth of $1 over the full history, on a log scale.
 *
 * Log, because a century of compounding on a linear axis is a flat line and a
 * hockey stick, and the decades where a theme stopped working vanish into the
 * flat part. On a log axis equal slopes are equal returns, whenever they happen.
 */
export function Sparkline({
  points,
  width = 160,
  height = 32,
}: {
  points: Point[];
  width?: number;
  height?: number;
}) {
  if (points.length < 2) return null;
  const logs = points.map((p) => Math.log(p.value));
  const lo = Math.min(0, ...logs);
  const hi = Math.max(0, ...logs);
  const span = hi - lo || 1;
  const x = (i: number) => (i / (points.length - 1)) * width;
  const y = (l: number) => height - 2 - ((l - lo) / span) * (height - 4);
  const d = logs.map((l, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(l).toFixed(1)}`).join("");
  return (
    <svg width={width} height={height} aria-hidden="true" className="block shrink-0">
      <line
        x1={0}
        x2={width}
        y1={y(0)}
        y2={y(0)}
        stroke="var(--ground-line)"
        strokeWidth={1}
      />
      <path d={d} fill="none" stroke="var(--on-ground-soft)" strokeWidth={1.5} />
    </svg>
  );
}

// ── Cumulative ─────────────────────────────────────────────────────────────

/**
 * Growth of $1 in the theme's long-short portfolio, with a crosshair.
 *
 * Gridlines sit at the doublings and halvings (0.5, 1, 2, 4 …), which are the
 * only ticks that mean something on a log axis without arithmetic. The $1 line
 * is drawn heavier: above it the theme made money over the window, below it
 * it lost, and that is the first thing anyone wants to know.
 */
export function CumulativeChart({
  points,
  title,
}: {
  points: Point[];
  title: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const W = Math.max(width, 280);
  const H = 240;
  const PAD = { top: 16, right: 16, bottom: 28, left: 48 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  if (points.length < 2) {
    return <div ref={ref} />;
  }

  const logs = points.map((p) => Math.log2(p.value));
  const lo = Math.min(0, Math.floor(Math.min(...logs)));
  const hi = Math.max(1, Math.ceil(Math.max(...logs)));
  const x = (i: number) => PAD.left + (i / (points.length - 1)) * plotW;
  const y = (l: number) => PAD.top + plotH - ((l - lo) / (hi - lo)) * plotH;
  const d = logs.map((l, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(l).toFixed(1)}`).join("");

  // Ticks at powers of two; thinned so labels never collide.
  const step = Math.max(1, Math.ceil((hi - lo) / 6));
  const ticks: number[] = [];
  for (let t = lo; t <= hi; t += step) ticks.push(t);
  if (!ticks.includes(0)) ticks.push(0);

  // Year ticks: roughly one per 110px.
  const nYears = Math.max(2, Math.floor(plotW / 110));
  const yearIdx = Array.from({ length: nYears }, (_, k) =>
    Math.round((k / (nYears - 1)) * (points.length - 1)),
  );

  const last = points[points.length - 1]!;
  const h = hover != null ? points[hover] : null;

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - r.left;
    const i = Math.round(((px - PAD.left) / plotW) * (points.length - 1));
    setHover(Math.max(0, Math.min(points.length - 1, i)));
  };

  const fmtDollar = (v: number) => (v >= 10 ? `$${v.toFixed(0)}` : `$${v.toFixed(2)}`);

  return (
    <div ref={ref} className="relative">
      <svg
        width={W}
        height={H}
        role="img"
        aria-label={`${title}: $1 grew to ${fmtDollar(last.value)} between ${monthLabel(points[0]!.month)} and ${monthLabel(last.month)}.`}
        className="block touch-none text-on-ink-faint"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(t)}
              y2={y(t)}
              stroke={t === 0 ? "var(--on-ground-faint)" : "var(--ground-line)"}
              strokeWidth={t === 0 ? 1.5 : 1}
            />
            <text
              x={PAD.left - 8}
              y={y(t) + 4}
              textAnchor="end"
              fontSize={LABEL_PX}
              fill="currentColor"
            >
              {fmtDollar(2 ** t)}
            </text>
          </g>
        ))}
        {yearIdx.map((i) => (
          <text
            key={i}
            x={x(i)}
            y={H - 8}
            textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}
            fontSize={LABEL_PX}
            fill="currentColor"
          >
            {/* The first point is the starting dollar, dated the month before
              * the first return; label the axis from the first real month. */}
            {points[Math.max(i, 1)]!.month.slice(0, 4)}
          </text>
        ))}

        <path d={d} fill="none" stroke="var(--strong)" strokeWidth={2} strokeLinejoin="round" />

        {h && hover != null && (
          <g pointerEvents="none">
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={PAD.top}
              y2={PAD.top + plotH}
              stroke="var(--on-ground-faint)"
              strokeDasharray="3 3"
            />
            <circle
              cx={x(hover)}
              cy={y(logs[hover]!)}
              r={4}
              fill="var(--strong)"
              stroke="var(--ground)"
              strokeWidth={2}
            />
          </g>
        )}
      </svg>

      {h && hover != null && (
        <div
          className="pointer-events-none absolute top-0 z-10 rounded border border-ink-line bg-ink-raised px-sm py-xs shadow-elev-1"
          style={{
            left: Math.min(Math.max(x(hover) + 12, 0), W - 180),
          }}
        >
          <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
            {monthLabel(h.month)}
          </p>
          <p className="tabular text-body-xs text-bone">$1 → {fmtDollar(h.value)}</p>
          <p className="tabular text-body-xs text-on-ink-soft">
            {h.ret == null ? "no return this month" : `month ${signedPct(h.ret)}`}
          </p>
        </div>
      )}
    </div>
  );
}

// ── Replication ────────────────────────────────────────────────────────────

/**
 * Each factor's Sharpe ratio inside the sample its paper studied (hollow) and
 * after that sample ended (solid).
 *
 * This is the paper's question asked one factor at a time. A line running left
 * is a premium that shrank once people knew about it; one crossing zero is a
 * result that did not survive. Most run left — which is expected, and is not
 * the same as failing — so the verdict is about the sign, not the size.
 */
export function ReplicationChart({ rows }: { rows: FactorRow[] }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const data = rows.filter(
    (r) => r.in_sample?.sharpe != null && r.post_sample?.sharpe != null,
  );
  const ROW = 26;
  const W = Math.max(width, 320);
  const narrow = W < 560;
  const LABEL_W = narrow ? 128 : 220;
  const VERDICT_W = 64;
  const PAD = { top: 22, bottom: 28 };
  const H = PAD.top + data.length * ROW + PAD.bottom;
  const plotL = LABEL_W + 12;
  const plotR = W - VERDICT_W - 8;

  if (data.length === 0) return <div ref={ref} />;

  const vals = data.flatMap((r) => [r.in_sample!.sharpe!, r.post_sample!.sharpe!]);
  const lo = Math.min(-0.2, Math.floor(Math.min(...vals) * 5) / 5);
  const hi = Math.max(0.4, Math.ceil(Math.max(...vals) * 5) / 5);
  const x = (v: number) => plotL + ((v - lo) / (hi - lo)) * (plotR - plotL);
  const y = (i: number) => PAD.top + i * ROW + ROW / 2;

  const truncate = (s: string) => {
    const max = Math.floor(LABEL_W / 7);
    return s.length > max ? `${s.slice(0, max - 1)}…` : s;
  };

  const hv = hover != null ? data[hover] : null;

  return (
    <div ref={ref} className="relative">
      <svg
        width={W}
        height={H}
        role="img"
        aria-label={`Sharpe ratio of ${data.length} factors inside and after their original samples.`}
        className="block text-on-ink-faint"
        onPointerLeave={() => setHover(null)}
      >
        {/* Zero: the line a premium has to stay right of to count as held. */}
        <line
          x1={x(0)}
          x2={x(0)}
          y1={PAD.top - 6}
          y2={H - PAD.bottom}
          stroke="var(--on-ground-faint)"
          strokeWidth={1.5}
        />
        <text x={x(0)} y={12} textAnchor="middle" fontSize={LABEL_PX} fill="currentColor">
          0
        </text>
        <text x={plotL} y={H - 8} fontSize={LABEL_PX} fill="currentColor">
          {fixed(lo, 1)}
        </text>
        <text x={plotR} y={H - 8} textAnchor="end" fontSize={LABEL_PX} fill="currentColor">
          {fixed(hi, 1)} Sharpe
        </text>

        {data.map((r, i) => {
          const a = r.in_sample!.sharpe!;
          const b = r.post_sample!.sharpe!;
          const held = (r.post_sample!.ann_return ?? 0) > 0;
          const c = held ? "var(--verdigris)" : "var(--oxide)";
          const yy = y(i);
          const on = hover === i;
          return (
            <g
              key={r.id}
              onPointerEnter={() => setHover(i)}
              opacity={hover == null || on ? 1 : 0.45}
            >
              {/* Hit target: the whole row, not the 4px dot. */}
              <rect x={0} y={yy - ROW / 2} width={W} height={ROW} fill="transparent" />
              <text
                x={LABEL_W}
                y={yy + 4}
                textAnchor="end"
                fontSize={LABEL_PX}
                fill={on ? "var(--strong)" : "var(--on-ground-soft)"}
              >
                {truncate(r.name)}
              </text>
              <line x1={x(a)} x2={x(b)} y1={yy} y2={yy} stroke={c} strokeWidth={2} opacity={0.6} />
              <circle cx={x(a)} cy={yy} r={4} fill="var(--ground)" stroke={c} strokeWidth={1.5} />
              <circle cx={x(b)} cy={yy} r={4.5} fill={c} stroke="var(--ground)" strokeWidth={2} />
              <text
                x={W - 4}
                y={yy + 4}
                textAnchor="end"
                fontSize={LABEL_PX}
                fill="var(--on-ground-soft)"
              >
                {held ? "held" : "did not"}
              </text>
            </g>
          );
        })}
      </svg>

      {hv && hover != null && (
        <div
          className="pointer-events-none absolute z-10 w-[260px] rounded border border-ink-line bg-ink-raised px-sm py-xs shadow-elev-1"
          style={{
            top: y(hover) + 14,
            left: Math.min(Math.max(plotL, x(hv.post_sample!.sharpe!) - 130), W - 264),
          }}
        >
          <p className="text-body-xs font-semibold text-bone">{hv.name}</p>
          <p className="text-body-xs text-on-ink-soft">
            {hv.cite ?? "No citation recorded"}
            {hv.in_sample_years && ` · sample ${hv.in_sample_years[0]}–${hv.in_sample_years[1]}`}
          </p>
          <p className="tabular mt-2xs text-body-xs text-on-ink">
            Sharpe {fixed(hv.in_sample!.sharpe)} in sample → {fixed(hv.post_sample!.sharpe)} after
          </p>
          <p className="tabular text-body-xs text-on-ink-soft">
            {signedPct(hv.post_sample!.ann_return)} a year over {Math.round(hv.post_sample!.months / 12)}{" "}
            years after
            {hv.original_t != null && ` · original t ${fixed(hv.original_t)}`}
          </p>
        </div>
      )}
    </div>
  );
}
