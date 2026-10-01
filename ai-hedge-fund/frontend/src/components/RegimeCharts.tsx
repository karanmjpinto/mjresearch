import { useMemo, useState } from "react";
import { useWidth } from "./FactorCharts";
import {
  num,
  pct,
  regimeColour,
  regimeTint,
  shortDate,
  signed,
  type RegimeAnalysis,
  type RegimeCentroid,
  type RegimeWindow,
} from "@/lib/regimes";

/**
 * The drawings on the Regimes tab. Hand-built SVG like `FactorCharts`, drawn
 * at the width they are shown at so label type stays a real 12px rather than
 * being scaled below the floor.
 *
 * Four charts, each answering a different question, in the order a reader
 * needs them:
 *
 *   RegimePath          when — the price path, coloured by regime
 *   RegimeScatter       what separated them — every window in mean-variance
 *   RegimeShapes        what was actually clustered — the two barycentres
 *   SeparationBars      whether to believe any of it
 *
 * `RegimeShapes` is the one with no equivalent elsewhere in the app, and the
 * one worth looking at longest: the method clusters whole distributions, so
 * the distributions are what it should be judged on. A mean-variance dot can
 * hide a fat left tail; a quantile curve cannot.
 */

const LABEL_PX = 12;

// ── 1. The price path, coloured by regime ─────────────────────────────────

/**
 * Ten years of closes with the turbulent stretches shaded behind them.
 *
 * This is the paper's Figure 2 and the chart that makes the method legible at
 * all: if the shading does not land on the crashes a reader remembers, nothing
 * further on the page is worth reading.
 *
 * Log price, because a decade of compounding on a linear axis compresses the
 * early years into a flat line — and the early years are where half the
 * regimes are.
 */
export function RegimePath({ data }: { data: RegimeAnalysis }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const { dates, closes, stress } = data.path;
  const k = data.params.k;

  const W = Math.max(width, 320);
  const H = 300;
  const PAD = { top: 16, right: 12, bottom: 30, left: 52 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const geom = useMemo(() => {
    const vals = closes.map((c) => (c && c > 0 ? Math.log(c) : NaN));
    const finite = vals.filter(Number.isFinite);
    if (finite.length < 2) return null;
    const lo = Math.min(...finite);
    const hi = Math.max(...finite);
    const span = hi - lo || 1;
    const x = (i: number) => PAD.left + (i / (vals.length - 1)) * plotW;
    const y = (v: number) => PAD.top + plotH - ((v - lo) / span) * plotH;
    const d = vals
      .map((v, i) => (Number.isFinite(v) ? `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}` : ""))
      .join("");

    // Contiguous stressed bands, from the per-day share. Half is the
    // threshold because a day is claimed by several overlapping windows and
    // the majority of them is the only non-arbitrary cut.
    const bands: { from: number; to: number }[] = [];
    let open: number | null = null;
    stress.forEach((s, i) => {
      const on = s != null && s >= 0.5;
      if (on && open == null) open = i;
      if (!on && open != null) {
        bands.push({ from: open, to: i });
        open = null;
      }
    });
    if (open != null) bands.push({ from: open, to: stress.length - 1 });

    return { x, y, d, lo, hi, bands, vals };
  }, [closes, stress, plotW, plotH, PAD.left, PAD.top]);

  if (!geom) return <div ref={ref} />;

  /* One tick per year, not N evenly-spaced indices. Even spacing put two ticks
   * inside the same calendar year and the axis printed "2022 2022" — a reader
   * checking a date against a shaded band then has no idea which is which. */
  const tickIdx = (() => {
    const wanted = Math.max(2, Math.floor(plotW / 100));
    const firstOf = new Map<string, number>();
    dates.forEach((d, i) => {
      const yr = d.slice(0, 4);
      if (!firstOf.has(yr)) firstOf.set(yr, i);
    });
    const years = [...firstOf.entries()];
    const step = Math.max(1, Math.ceil(years.length / wanted));
    const picked = years.filter((_, i) => i % step === 0).map(([, i]) => i);

    /* A history starting mid-year puts its first two ticks weeks apart — KO
     * begins in November, so 2019 and 2020 printed on top of each other. Keep
     * a tick only if it clears the previous one by a label's width. */
    const minGap = 40;
    const perIdx = plotW / Math.max(1, dates.length - 1);
    const spaced: number[] = [];
    for (const i of picked) {
      if (!spaced.length || (i - spaced[spaced.length - 1]!) * perIdx >= minGap) spaced.push(i);
    }
    return spaced;
  })();
  const priceTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => geom.lo + f * (geom.hi - geom.lo));

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.round(((e.clientX - r.left - PAD.left) / plotW) * (dates.length - 1));
    setHover(Math.max(0, Math.min(dates.length - 1, i)));
  };

  const hv = hover == null ? null : hover;
  const hvStress = hv == null ? null : stress[hv];
  const hvName =
    hvStress == null
      ? "not measured"
      : hvStress >= 0.5
        ? data.centroids[k - 1]!.name
        : data.centroids[0]!.name;

  return (
    <div ref={ref} className="relative">
      <svg
        width={W}
        height={H}
        role="img"
        aria-label={`${data.ticker} price from ${dates[0]} to ${dates[dates.length - 1]}, with ${geom.bands.length} turbulent stretches shaded.`}
        className="block touch-none text-on-ink-faint"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {/* Turbulent stretches behind the line, not on it: the price is the
          * measured thing and the regime is the reading of it. */}
        {geom.bands.map((b, i) => (
          <rect
            key={i}
            x={geom.x(b.from)}
            y={PAD.top}
            width={Math.max(1.5, geom.x(b.to) - geom.x(b.from))}
            height={plotH}
            fill={regimeTint(k - 1, k, 0.22)}
          />
        ))}

        {priceTicks.map((t, i) => (
          <g key={i}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={geom.y(t)}
              y2={geom.y(t)}
              stroke="var(--ground-line)"
              strokeWidth={1}
            />
            <text
              x={PAD.left - 8}
              y={geom.y(t) + 4}
              textAnchor="end"
              fontSize={LABEL_PX}
              fill="currentColor"
            >
              {Math.exp(t) >= 100 ? Math.exp(t).toFixed(0) : Math.exp(t).toFixed(1)}
            </text>
          </g>
        ))}

        {tickIdx.map((i) => (
          <text
            key={i}
            x={geom.x(i)}
            y={H - 8}
            textAnchor={i === 0 ? "start" : i === dates.length - 1 ? "end" : "middle"}
            fontSize={LABEL_PX}
            fill="currentColor"
          >
            {dates[i]?.slice(0, 4)}
          </text>
        ))}

        <path d={geom.d} fill="none" stroke="var(--strong)" strokeWidth={1.5} strokeLinejoin="round" />

        {hv != null && Number.isFinite(geom.vals[hv]!) && (
          <g pointerEvents="none">
            <line
              x1={geom.x(hv)}
              x2={geom.x(hv)}
              y1={PAD.top}
              y2={PAD.top + plotH}
              stroke="var(--on-ground-faint)"
              strokeDasharray="3 3"
            />
            <circle
              cx={geom.x(hv)}
              cy={geom.y(geom.vals[hv]!)}
              r={4}
              fill="var(--strong)"
              stroke="var(--ground)"
              strokeWidth={2}
            />
          </g>
        )}
      </svg>

      {hv != null && (
        <div
          className="pointer-events-none absolute top-0 z-10 w-[190px] rounded border border-ink-line bg-ink-raised px-sm py-xs shadow-elev-1"
          style={{ left: Math.min(Math.max(geom.x(hv) + 12, 0), W - 194) }}
        >
          <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
            {dates[hv]}
          </p>
          <p className="tabular text-body-xs text-bone">{num(closes[hv], 2)}</p>
          <p className="text-body-xs text-on-ink-soft">
            {hvName}
            {hvStress != null && hvStress > 0 && hvStress < 1 && (
              <span className="tabular"> · {Math.round(hvStress * 100)}% of windows</span>
            )}
          </p>
        </div>
      )}
    </div>
  );
}

// ── 2. Every window in mean-variance space ────────────────────────────────

/**
 * One dot per window: annualised volatility across, annualised mean up.
 *
 * The paper's Figure 1, and it is here to show *where the split fell* — a
 * near-vertical boundary would mean the clustering found nothing a volatility
 * threshold could not have found, which is a real possibility on a calm name
 * and one a reader is entitled to check.
 *
 * Centroids are crosses. They sit where they sit because a barycentre is a
 * median of order statistics, not a mean of the dots, so a cross need not land
 * in the middle of its cloud — and when it visibly doesn't, that is the
 * robustness working rather than a bug.
 */
export function RegimeScatter({ data }: { data: RegimeAnalysis }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const rows = data.windows_detail;
  const k = data.params.k;
  const W = Math.max(width, 280);
  const H = 260;
  const PAD = { top: 14, right: 14, bottom: 34, left: 54 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const pts = rows
    .map((r, i) => ({ ...r, i }))
    .filter((r) => r.vol_pct != null && r.mean_day_pct != null);
  if (pts.length === 0) return <div ref={ref} />;

  const vols = pts.map((p) => p.vol_pct!);
  const means = pts.map((p) => p.mean_day_pct!);
  const vLo = 0;
  const vHi = Math.max(...vols) * 1.06;
  const mLo = Math.min(...means, 0) * 1.08;
  const mHi = Math.max(...means, 0) * 1.08;

  const x = (v: number) => PAD.left + ((v - vLo) / (vHi - vLo || 1)) * plotW;
  const y = (m: number) => PAD.top + plotH - ((m - mLo) / (mHi - mLo || 1)) * plotH;

  const hv = hover == null ? null : pts.find((p) => p.i === hover);

  return (
    <div ref={ref} className="relative">
      <svg
        width={W}
        height={H}
        role="img"
        aria-label={`${pts.length} windows plotted by annualised volatility and average daily return, coloured by regime.`}
        className="block text-on-ink-faint"
        onPointerLeave={() => setHover(null)}
      >
        {/* Zero return: above it the window made money, below it lost. */}
        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={y(0)}
          y2={y(0)}
          stroke="var(--on-ground-faint)"
          strokeWidth={1}
        />
        <text x={PAD.left - 8} y={y(0) + 4} textAnchor="end" fontSize={LABEL_PX} fill="currentColor">
          0%
        </text>
        <text
          x={PAD.left - 8}
          y={y(mHi) + 10}
          textAnchor="end"
          fontSize={LABEL_PX}
          fill="currentColor"
        >
          {signed(mHi, 2)}
        </text>
        <text
          x={PAD.left - 8}
          y={y(mLo) - 2}
          textAnchor="end"
          fontSize={LABEL_PX}
          fill="currentColor"
        >
          {signed(mLo, 2)}
        </text>
        <text x={W - PAD.right} y={H - 8} textAnchor="end" fontSize={LABEL_PX} fill="currentColor">
          {pct(vHi, 0)} volatility
        </text>
        <text x={PAD.left} y={H - 8} fontSize={LABEL_PX} fill="currentColor">
          average day, up
        </text>

        {pts.map((p) => (
          <circle
            key={p.i}
            cx={x(p.vol_pct!)}
            cy={y(p.mean_day_pct!)}
            r={hover === p.i ? 5 : 3}
            fill={regimeColour(p.label, k)}
            opacity={hover == null || hover === p.i ? 0.72 : 0.28}
            onPointerEnter={() => setHover(p.i)}
          />
        ))}

        {data.centroids.map((c) =>
          c.vol_pct == null || c.mean_day_pct == null ? null : (
            <g key={c.label} pointerEvents="none">
              <line
                x1={x(c.vol_pct) - 9}
                x2={x(c.vol_pct) + 9}
                y1={y(c.mean_day_pct)}
                y2={y(c.mean_day_pct)}
                stroke="var(--ground)"
                strokeWidth={6}
              />
              <line
                x1={x(c.vol_pct)}
                x2={x(c.vol_pct)}
                y1={y(c.mean_day_pct) - 9}
                y2={y(c.mean_day_pct) + 9}
                stroke="var(--ground)"
                strokeWidth={6}
              />
              <line
                x1={x(c.vol_pct) - 9}
                x2={x(c.vol_pct) + 9}
                y1={y(c.mean_day_pct)}
                y2={y(c.mean_day_pct)}
                stroke={regimeColour(c.label, k)}
                strokeWidth={3}
              />
              <line
                x1={x(c.vol_pct)}
                x2={x(c.vol_pct)}
                y1={y(c.mean_day_pct) - 9}
                y2={y(c.mean_day_pct) + 9}
                stroke={regimeColour(c.label, k)}
                strokeWidth={3}
              />
            </g>
          ),
        )}
      </svg>

      {hv && (
        <div
          className="pointer-events-none absolute z-10 w-[210px] rounded border border-ink-line bg-ink-raised px-sm py-xs shadow-elev-1"
          style={{
            top: Math.min(y(hv.mean_day_pct!) + 12, H - 86),
            left: Math.min(Math.max(x(hv.vol_pct!) - 100, 0), W - 214),
          }}
        >
          <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
            {shortDate(hv.start)} – {shortDate(hv.end)}
          </p>
          <p className="tabular text-body-xs text-bone">
            {pct(hv.vol_pct)} vol · {signed(hv.mean_day_pct, 2)} an average day
          </p>
          <p className="tabular text-body-xs text-on-ink-soft">
            skew {num(hv.skew)} · fat tails {num(hv.kurtosis)}
          </p>
          <p className="text-body-xs text-on-ink-soft">
            {data.centroids[hv.label]?.name ?? "—"}
          </p>
        </div>
      )}
    </div>
  );
}

// ── 3. The barycentres themselves ─────────────────────────────────────────

/**
 * What the algorithm actually clusters: the typical daily return distribution
 * of each regime, drawn as a quantile curve.
 *
 * Read it as "the n-th worst day in a hundred". The left end is the part that
 * matters — two regimes can share a volatility and differ entirely in how bad
 * their bad days get, and that difference is exactly what a variance threshold
 * cannot see and what this method is for.
 *
 * Quantiles rather than a histogram: a barycentre *is* a sorted vector of
 * order statistics, so plotting it directly adds no binning choice of our own.
 */
export function RegimeShapes({ centroids, k }: { centroids: RegimeCentroid[]; k: number }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const W = Math.max(width, 280);
  const H = 260;
  const PAD = { top: 16, right: 14, bottom: 34, left: 52 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const series = centroids
    .map((c) => ({ c, q: c.quantiles.map((v) => (v == null ? NaN : v * 100)) }))
    .filter((s) => s.q.some(Number.isFinite));
  if (series.length === 0) return <div ref={ref} />;

  const all = series.flatMap((s) => s.q).filter(Number.isFinite);
  const lim = Math.max(Math.abs(Math.min(...all)), Math.abs(Math.max(...all))) * 1.05 || 1;
  const n = series[0]!.q.length;

  const x = (i: number) => PAD.left + (i / (n - 1)) * plotW;
  const y = (v: number) => PAD.top + plotH / 2 - (v / lim) * (plotH / 2);

  const hi = hover == null ? null : Math.max(0, Math.min(n - 1, hover));

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    setHover(Math.round(((e.clientX - r.left - PAD.left) / plotW) * (n - 1)));
  };

  return (
    <div ref={ref} className="relative">
      <svg
        width={W}
        height={H}
        role="img"
        aria-label={`Typical daily return distribution of each regime, from worst day to best. ${series
          .map((s) => `${s.c.name}: worst ${pct(s.c.worst_day_pct)}`)
          .join("; ")}.`}
        className="block touch-none text-on-ink-faint"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={y(0)}
          y2={y(0)}
          stroke="var(--on-ground-faint)"
          strokeWidth={1}
        />
        {[lim, -lim].map((t) => (
          <text
            key={t}
            x={PAD.left - 8}
            y={y(t) + (t > 0 ? 10 : -2)}
            textAnchor="end"
            fontSize={LABEL_PX}
            fill="currentColor"
          >
            {signed(t, 1)}
          </text>
        ))}
        <text x={PAD.left - 8} y={y(0) + 4} textAnchor="end" fontSize={LABEL_PX} fill="currentColor">
          0%
        </text>
        <text x={PAD.left} y={H - 8} fontSize={LABEL_PX} fill="currentColor">
          worst day
        </text>
        <text x={W - PAD.right} y={H - 8} textAnchor="end" fontSize={LABEL_PX} fill="currentColor">
          best day
        </text>

        {series.map(({ c, q }) => {
          const d = q
            .map((v, i) => (Number.isFinite(v) ? `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}` : ""))
            .join("");
          return (
            <g key={c.label}>
              <path
                d={`${d}L${x(n - 1).toFixed(1)},${y(0).toFixed(1)}L${x(0).toFixed(1)},${y(0).toFixed(1)}Z`}
                fill={regimeTint(c.label, k, 0.14)}
              />
              <path d={d} fill="none" stroke={regimeColour(c.label, k)} strokeWidth={2} />
            </g>
          );
        })}

        {hi != null && (
          <line
            x1={x(hi)}
            x2={x(hi)}
            y1={PAD.top}
            y2={PAD.top + plotH}
            stroke="var(--on-ground-faint)"
            strokeDasharray="3 3"
            pointerEvents="none"
          />
        )}
      </svg>

      {hi != null && (
        <div
          className="pointer-events-none absolute top-0 z-10 w-[200px] rounded border border-ink-line bg-ink-raised px-sm py-xs shadow-elev-1"
          style={{ left: Math.min(Math.max(x(hi) + 12, 0), W - 204) }}
        >
          <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
            {hi === 0
              ? "worst day"
              : hi === n - 1
                ? "best day"
                : `${Math.round((hi / (n - 1)) * 100)}th percentile day`}
          </p>
          {series.map(({ c, q }) => (
            <p key={c.label} className="tabular text-body-xs text-on-ink">
              <span style={{ color: regimeColour(c.label, k) }}>■</span> {c.name}{" "}
              {signed(q[hi], 2)}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

// ── 4. Whether to believe any of it ───────────────────────────────────────

/**
 * The separation ratio for this method and for the rule it replaces.
 *
 * Both were scored on identical windows with an identical kernel, so the two
 * bars are comparable and the comparison is the point. The 1.0 line is where
 * a labelling stops meaning anything: below it, windows resemble the *other*
 * cluster as much as their own.
 *
 * Shown even when the old rule wins. A method that only reports the cases it
 * wins is not evidence.
 */
export function SeparationBars({
  rows,
}: {
  rows: { name: string; ratio: number | null; note: string }[];
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const W = Math.max(width, 260);
  const ROW = 46;
  const H = rows.length * ROW + 26;
  const LABEL_W = Math.min(150, Math.max(104, W * 0.32));
  const plotL = LABEL_W + 10;
  const plotR = W - 46;

  const hi = Math.max(2.2, ...rows.map((r) => (r.ratio && Number.isFinite(r.ratio) ? r.ratio : 0)) ) * 1.08;
  const x = (v: number) => plotL + (Math.max(0, v) / hi) * (plotR - plotL);

  return (
    <div ref={ref}>
      <svg
        width={W}
        height={H}
        role="img"
        aria-label={rows
          .map((r) => `${r.name}: separation ratio ${num(r.ratio)}`)
          .join(". ")}
        className="block text-on-ink-faint"
      >
        {rows.map((r, i) => {
          const yy = i * ROW + 20;
          const good = r.ratio != null && r.ratio > 1;
          const fill = good ? "var(--cobalt)" : "var(--oxide)";
          return (
            <g key={r.name}>
              <text
                x={LABEL_W}
                y={yy + 4}
                textAnchor="end"
                fontSize={LABEL_PX}
                fill="var(--on-ground-soft)"
              >
                {r.name}
              </text>
              <rect
                x={plotL}
                y={yy - 7}
                width={Math.max(2, x(r.ratio ?? 0) - plotL)}
                height={14}
                rx={2}
                fill={fill}
              />
              <text
                x={x(r.ratio ?? 0) + 8}
                y={yy + 4}
                fontSize={LABEL_PX}
                fill="var(--strong)"
                className="tabular"
              >
                {num(r.ratio)}
              </text>
              <text x={plotL} y={yy + 22} fontSize={LABEL_PX} fill="currentColor">
                {r.note}
              </text>
            </g>
          );
        })}

        {/* The line a labelling has to clear to mean anything at all. */}
        <line x1={x(1)} x2={x(1)} y1={6} y2={H - 12} stroke="var(--on-ground-faint)" strokeWidth={1.5} />
        <text x={x(1)} y={H - 2} textAnchor="middle" fontSize={LABEL_PX} fill="currentColor">
          1.0 — no separation
        </text>
      </svg>
    </div>
  );
}

// ── the episode strip ─────────────────────────────────────────────────────

/**
 * Every dated stretch, as one proportional bar.
 *
 * A compact answer to "how much of the decade was turbulent, and when" that
 * the price chart gives only by eye. Each segment is also a row in the table
 * below it, so the colour is never the only way to read it.
 */
export function EpisodeStrip({ data }: { data: RegimeAnalysis }) {
  const total = data.episodes.reduce((s, e) => s + e.days, 0) || 1;
  const k = data.params.k;
  return (
    <div
      className="flex h-3 w-full overflow-hidden rounded"
      role="img"
      aria-label={`${data.episodes.length} regime stretches between ${data.coverage.first_date} and ${data.coverage.last_date}.`}
    >
      {data.episodes.map((e, i) => (
        <div
          key={`${e.start}-${i}`}
          style={{
            width: `${(e.days / total) * 100}%`,
            background: regimeColour(e.label, k),
          }}
          title={`${e.name}: ${e.start} to ${e.end}`}
        />
      ))}
    </div>
  );
}

export type { RegimeWindow };
