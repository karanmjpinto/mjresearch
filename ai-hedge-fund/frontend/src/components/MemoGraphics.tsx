import type { MacroPoint } from "@/lib/api";
import type { Quadrant, Signal, Tone } from "@/lib/timing";

/**
 * The memo's pictures. Plain SVG rather than the chart library: these print,
 * and a ResponsiveContainer measures zero width inside a print layout. Colours
 * are the canvas-ground tokens, read through `var()`, so they follow the
 * palette and survive print-color-adjust.
 */

export const TONE_COLOR: Record<Tone, string> = {
  go: "var(--verdigris-paper)",
  wait: "var(--cadmium-paper)",
  stop: "var(--oxide-paper)",
};
export const TONE_WORD: Record<Tone, string> = { go: "Supports", wait: "Mixed", stop: "Against" };

const INK = "var(--on-canvas)";
const SOFT = "var(--on-canvas-soft)";
const FAINT = "var(--on-canvas-faint)";
const LINE = "var(--canvas-deep)";

/** A filled tag carrying the tone word, so the colour is never the only cue. */
export function ToneTag({ tone }: { tone: Tone }) {
  return (
    <span
      className="inline-block shrink-0 px-2xs font-display text-label uppercase tracking-label text-on-accent-light"
      style={{ background: TONE_COLOR[tone] }}
    >
      {TONE_WORD[tone]}
    </span>
  );
}

export function SignalList({ signals }: { signals: Signal[] }) {
  return (
    <ul className="grid gap-x-md sm:grid-cols-2 print:grid-cols-2">
      {signals.map((s) => (
        <li
          key={s.label}
          className="flex items-start gap-xs border-b border-canvas-deep py-2xs"
          style={{ borderLeft: `3px solid ${TONE_COLOR[s.tone]}`, paddingLeft: 8 }}
        >
          <div className="min-w-0 flex-1">
            <p className="font-display text-label uppercase tracking-label text-on-canvas-soft">{s.label}</p>
            <p className="text-body-xs text-on-canvas">{s.reading}</p>
          </div>
          <ToneTag tone={s.tone} />
        </li>
      ))}
    </ul>
  );
}

const sma = (xs: number[], n: number, i: number) =>
  i + 1 < n ? null : xs.slice(i + 1 - n, i + 1).reduce((a, b) => a + b, 0) / n;

/** A year of closes with the 50- and 200-day averages, drawn from a longer history. */
export function PriceChart({ rows, height = 180 }: { rows: { date: string; close: number }[]; height?: number }) {
  const W = 800;
  const H = height;
  const pad = { l: 44, r: 8, t: 8, b: 20 };
  const closes = rows.map((r) => r.close);
  const start = Math.max(0, rows.length - 252);
  const idx = rows.slice(start).map((_, k) => start + k);
  if (idx.length < 20) return null;

  const s50 = idx.map((i) => sma(closes, 50, i));
  const s200 = idx.map((i) => sma(closes, 200, i));
  const vals = [...idx.map((i) => closes[i]!), ...s50, ...s200].filter((v): v is number => v != null);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const x = (k: number) => pad.l + (k / (idx.length - 1)) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - (v - lo) / (hi - lo || 1)) * (H - pad.t - pad.b);
  const path = (ys: (number | null)[]) =>
    ys
      .map((v, k) => (v == null ? null : `${x(k).toFixed(1)},${y(v).toFixed(1)}`))
      .filter(Boolean)
      .map((pt, j) => `${j ? "L" : "M"}${pt}`)
      .join("");
  const last = closes[idx[idx.length - 1]!]!;
  const ticks = [lo, (lo + hi) / 2, hi];
  const first = rows[idx[0]!]!.date.slice(0, 7);
  const end = rows[idx[idx.length - 1]!]!.date.slice(0, 7);

  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`Price over the last year, last close ${last.toFixed(2)}`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke={LINE} />
            <text x={pad.l - 6} y={y(t) + 4} textAnchor="end" fontSize="11" fill={FAINT}>
              {t.toFixed(0)}
            </text>
          </g>
        ))}
        <text x={pad.l} y={H - 4} fontSize="11" fill={FAINT}>{first}</text>
        <text x={W - pad.r} y={H - 4} fontSize="11" fill={FAINT} textAnchor="end">{end}</text>
        <path d={path(s200)} fill="none" stroke="var(--oxide-paper)" strokeWidth="1.5" strokeDasharray="5 3" />
        <path d={path(s50)} fill="none" stroke="var(--cadmium-paper)" strokeWidth="1.5" />
        <path d={path(idx.map((i) => closes[i]!))} fill="none" stroke="var(--cobalt-paper)" strokeWidth="2" />
        <circle cx={x(idx.length - 1)} cy={y(last)} r="3.5" fill="var(--cobalt-paper)" />
      </svg>
      <figcaption className="flex flex-wrap gap-x-md text-body-xs text-on-canvas-soft">
        <Key color="var(--cobalt-paper)">Close</Key>
        <Key color="var(--cadmium-paper)">50-day average</Key>
        <Key color="var(--oxide-paper)" dashed>200-day average</Key>
      </figcaption>
    </figure>
  );
}

function Key({ color, dashed, children }: { color: string; dashed?: boolean; children: string }) {
  return (
    <span className="inline-flex items-center gap-2xs">
      <svg width="18" height="6" aria-hidden="true">
        <line x1="0" x2="18" y1="3" y2="3" stroke={color} strokeWidth="2" strokeDasharray={dashed ? "5 3" : undefined} />
      </svg>
      {children}
    </span>
  );
}

export type FieldRow = { label: string; low: number; high: number; mid?: number; color: string };

/** The valuation football field: each method's range, with today's price as a line. */
export function FootballField({ rows, price }: { rows: FieldRow[]; price: number | null }) {
  if (rows.length === 0) return null;
  // A wide viewBox at fixed font sizes: the bars stay thin and the labels small on paper.
  const W = 900;
  const rowH = 20;
  const labelW = 130;
  const H = rows.length * rowH + 22;
  const all = [...rows.flatMap((r) => [r.low, r.high]), ...(price ? [price] : [])];
  const lo = Math.min(...all) * 0.95;
  const hi = Math.max(...all) * 1.05;
  const x = (v: number) => labelW + ((v - lo) / (hi - lo)) * (W - labelW - 50);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Value ranges by method against the current price">
      {rows.map((r, i) => {
        const cy = i * rowH + 12;
        return (
          <g key={r.label}>
            <text x={0} y={cy + 4} fontSize="12" fill={SOFT}>{r.label}</text>
            <rect x={x(r.low)} y={cy - 7} width={Math.max(2, x(r.high) - x(r.low))} height={14} fill={r.color} opacity="0.85" />
            {r.mid != null && <line x1={x(r.mid)} x2={x(r.mid)} y1={cy - 7} y2={cy + 7} stroke="var(--paper)" strokeWidth="2" />}
            <text x={x(r.high) + 4} y={cy + 4} fontSize="11" fill={FAINT}>{`${r.low.toFixed(0)}–${r.high.toFixed(0)}`}</text>
          </g>
        );
      })}
      {price != null && (
        <g>
          <line x1={x(price)} x2={x(price)} y1={0} y2={H - 16} stroke={INK} strokeWidth="1.5" strokeDasharray="3 2" />
          <text x={x(price)} y={H - 3} fontSize="11" fill={INK} textAnchor="middle">{`Price ${price.toFixed(0)}`}</text>
        </g>
      )}
    </svg>
  );
}

const QUADRANTS: { q: Quadrant; gx: 0 | 1; gy: 0 | 1 }[] = [
  { q: "stagflation", gx: 0, gy: 0 },
  { q: "overheating", gx: 1, gy: 0 },
  { q: "recession", gx: 0, gy: 1 },
  { q: "goldilocks", gx: 1, gy: 1 },
];

/**
 * The macro map in miniature: growth across, inflation up, the company's point
 * with its error ring, and the quadrant the last year has been in shaded.
 */
export function MacroMini({ point, now }: { point: MacroPoint; now: Quadrant | null }) {
  const S = 180;
  const LIM = 0.6;
  const c = (v: number) => (S / 2) * (1 + Math.max(-LIM, Math.min(LIM, v)) / LIM);
  const half = S / 2;
  return (
    <figure>
      <svg viewBox={`-2 -2 ${S + 4} ${S + 4}`} className="w-full max-w-[200px]" role="img"
        aria-label={`Macro map: does best in ${point.quadrant}${now ? `, the last year was ${now}` : ""}`}>
        {QUADRANTS.map(({ q, gx, gy }) => (
          <g key={q}>
            <rect x={gx * half} y={gy * half} width={half} height={half}
              fill={q === now ? "var(--cadmium-paper)" : "transparent"} opacity={q === now ? 0.22 : 1} stroke={LINE} />
            {/* Outer corners, where the company's dot (near the centre) cannot sit on them. */}
            <text x={gx ? S - 5 : 5} y={gy ? S - 6 : 13} textAnchor={gx ? "end" : "start"} fontSize="10" fill={q === now ? INK : FAINT}>{q}</text>
          </g>
        ))}
        <circle cx={c(point.growth)} cy={S - c(point.inflation)} r={(point.standard_error / LIM) * half}
          fill="none" stroke="var(--oxide-paper)" strokeDasharray="3 2" />
        <circle cx={c(point.growth)} cy={S - c(point.inflation)} r="6" fill="var(--oxide-paper)" />
      </svg>
      <figcaption className="text-body-xs text-on-canvas-faint">
        Growth across, inflation up. Dot: this stock; ring: its error. Shaded: the last four quarters.
      </figcaption>
    </figure>
  );
}
