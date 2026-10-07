import { useMemo, useState } from "react";
import { useWidth } from "./FactorCharts";
import { shortDate, type BreadthResponse } from "@/lib/breadth";

/**
 * The divergence, drawn. Two stacked panels sharing one time axis.
 *
 * Top    the index and the advance-decline line, both rebased to 100 at the
 *        left edge. Rebasing is what makes the chart readable at all: the A-D
 *        line is a cumulative count in the tens of thousands and the index is
 *        a price, so on their own scales the two cannot share an axis and on
 *        two axes the gap between them can be made any size you like by
 *        choosing the ranges. One axis, one starting point, no choice left to
 *        make.
 * Bottom the share of members above their own 200-day average, against the
 *        threshold the signal uses. This is the panel the signal actually
 *        reads; the top one is the panel that makes it legible.
 *
 * Episode shading comes from the episode list rather than from a per-day flag,
 * so the bands and the table below can never disagree about when the signal
 * was on.
 */

const H_TOP = 190;
const H_BOT = 110;
const PAD = { top: 14, right: 14, bottom: 26, left: 46 };

export function BreadthChart({ data }: { data: BreadthResponse }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const { dates, index, ad_line, pct_above_200dma } = data.series;
  const W = Math.max(width, 320);
  const plotW = W - PAD.left - PAD.right;

  const geom = useMemo(() => {
    const rebase = (xs: (number | null)[]) => {
      const first = xs.find((v) => v != null && Number.isFinite(v));
      // The A-D line is rebased on its own first value, which can be zero or
      // negative — it is a cumulative count, not a price. Dividing by it would
      // flip or explode the series, so a non-positive base shifts to an offset
      // instead of a ratio and the two panels stay comparable in shape.
      if (first == null) return xs.map(() => null);
      if (first > 0) return xs.map((v) => (v == null ? null : (v / first) * 100));
      const span =
        Math.max(...xs.filter((v): v is number => v != null).map(Math.abs), 1) || 1;
      return xs.map((v) => (v == null ? null : 100 + ((v - first) / span) * 100));
    };

    const idx = rebase(index);
    const ad = rebase(ad_line);
    const both = [...idx, ...ad].filter((v): v is number => v != null);
    if (both.length < 4) return null;

    const lo = Math.min(...both);
    const hi = Math.max(...both);
    const span = hi - lo || 1;
    const x = (i: number) => PAD.left + (i / Math.max(1, dates.length - 1)) * plotW;
    const yTop = (v: number) =>
      PAD.top + (H_TOP - PAD.top - 6) - ((v - lo) / span) * (H_TOP - PAD.top - 6);
    const yBot = (v: number) =>
      H_TOP + 8 + (H_BOT - 26) - (Math.max(0, Math.min(100, v)) / 100) * (H_BOT - 26);

    const path = (xs: (number | null)[], y: (v: number) => number) => {
      let out = "";
      let open = false;
      xs.forEach((v, i) => {
        if (v == null) {
          open = false;
          return;
        }
        out += `${open ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
        open = true;
      });
      return out;
    };

    const at = new Map(dates.map((d, i) => [d, i]));
    const nearest = (iso: string, fallback: number) => {
      const exact = at.get(iso);
      if (exact != null) return exact;
      // An episode can start before the charted window, or on a session the
      // index did not trade. Clamp rather than drop: a band that silently
      // vanishes is worse than one that starts at the edge.
      const i = dates.findIndex((d) => d >= iso);
      return i === -1 ? fallback : i;
    };

    const bands = data.episodes
      .filter((e) => e.end >= dates[0]!)
      .map((e) => ({
        from: nearest(e.start, 0),
        to: nearest(e.end, dates.length - 1),
        label: e.start,
      }));

    return { x, yTop, yBot, idx, ad, lo, hi, bands, path };
  }, [dates, index, ad_line, plotW, data.episodes]);

  if (!geom) return <div ref={ref} />;

  const H = H_TOP + H_BOT;
  const floor = data.thresholds.floor;

  /* One tick per year, spaced so two never collide — the same rule as the
   * regime path, for the same reason. */
  const ticks = (() => {
    const firstOf = new Map<string, number>();
    dates.forEach((d, i) => {
      const yr = d.slice(0, 4);
      if (!firstOf.has(yr)) firstOf.set(yr, i);
    });
    const perIdx = plotW / Math.max(1, dates.length - 1);
    const out: number[] = [];
    for (const i of firstOf.values()) {
      if (!out.length || (i - out[out.length - 1]!) * perIdx >= 44) out.push(i);
    }
    return out;
  })();

  const hv = hover;

  return (
    <div ref={ref} className="w-full">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height={H}
        role="img"
        aria-label={`The index against the advance-decline line, and the share of members above their 200-day average, from ${shortDate(dates[0]!)} to ${shortDate(dates[dates.length - 1]!)}`}
        onPointerMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const i = Math.round(
            (((e.clientX - r.left) * (W / r.width) - PAD.left) / plotW) *
              (dates.length - 1),
          );
          setHover(Math.max(0, Math.min(dates.length - 1, i)));
        }}
        onPointerLeave={() => setHover(null)}
      >
        {geom.bands.map((b, i) => (
          <rect
            key={i}
            x={geom.x(b.from)}
            width={Math.max(1.5, geom.x(b.to) - geom.x(b.from))}
            y={PAD.top - 6}
            height={H - PAD.top - 12}
            className="fill-oxide/15"
          />
        ))}

        {ticks.map((i) => (
          <text
            key={i}
            x={geom.x(i)}
            y={H - 6}
            textAnchor="middle"
            className="fill-on-ink-soft font-display text-label"
          >
            {dates[i]!.slice(0, 4)}
          </text>
        ))}

        {/* top panel */}
        <path d={geom.path(geom.idx, geom.yTop)} fill="none" strokeWidth="1.5" className="stroke-cobalt" />
        <path d={geom.path(geom.ad, geom.yTop)} fill="none" strokeWidth="1.5" className="stroke-cadmium" />

        {/* bottom panel: the threshold the signal reads, and the series */}
        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={geom.yBot(floor)}
          y2={geom.yBot(floor)}
          strokeDasharray="3 3"
          className="stroke-oxide/70"
        />
        <text
          x={PAD.left - 6}
          y={geom.yBot(floor) + 4}
          textAnchor="end"
          className="fill-oxide font-display text-label tabular"
        >
          {floor}%
        </text>
        <path
          d={geom.path(pct_above_200dma, geom.yBot)}
          fill="none"
          strokeWidth="1.5"
          className="stroke-verdigris"
        />
        <text
          x={PAD.left - 6}
          y={geom.yBot(100) + 4}
          textAnchor="end"
          className="fill-on-ink-soft font-display text-label tabular"
        >
          100%
        </text>
        {/* The lower panel is the only one with a scale, and it carries two
          * labels rather than three: a zero here lands eight pixels from the
          * first year tick and the two read as one string. The panel is
          * anchored at zero and the threshold is drawn and labelled, which is
          * enough to place any point on it.
          *
          * The upper panel has no axis at all. It is two rebased series, so
          * its unit is one nobody can name, and printing a number there would
          * make a scale-free comparison look like a measurement. */}

        {hv != null && (
          <line
            x1={geom.x(hv)}
            x2={geom.x(hv)}
            y1={PAD.top - 6}
            y2={H - PAD.bottom + 4}
            className="stroke-on-ink-soft/50"
          />
        )}
      </svg>

      <dl className="mt-sm flex flex-wrap gap-md font-display text-label uppercase tracking-label text-on-ink-soft">
        <Key tone="bg-cobalt" label={`${data.source.index_symbol} (rebased)`} />
        <Key tone="bg-cadmium" label="Advance-decline line (rebased)" />
        <Key tone="bg-verdigris" label="% of members above their 200-day average" />
        <Key tone="bg-oxide/40" label="Divergence episode" />
      </dl>

      <p className="mt-xs font-display text-label text-on-ink-soft tabular">
        {hv == null
          ? `${shortDate(dates[0]!)} — ${shortDate(dates[dates.length - 1]!)}`
          : `${shortDate(dates[hv]!)} · ${pct_above_200dma[hv]?.toFixed(1) ?? "—"}% above their 200-day average`}
      </p>
    </div>
  );
}

function Key({ tone, label }: { tone: string; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span aria-hidden className={`inline-block h-2 w-4 ${tone}`} />
      <dt className="sr-only">series</dt>
      <dd>{label}</dd>
    </div>
  );
}
