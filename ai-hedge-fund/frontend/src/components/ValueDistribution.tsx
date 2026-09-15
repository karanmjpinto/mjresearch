/**
 * Ten thousand valuations, and where today's price falls among them.
 *
 * A single fair value invites one comparison — above or below the price — and
 * hides the only thing worth knowing, which is how wide the range is. A
 * distribution answers a better question: out of every draw the drivers allow,
 * how many landed above what the market is asking?
 *
 * Drawn rather than tabulated because the shape is the finding. The price line
 * either sits inside the mass or it sits off the end, and a column of
 * percentiles makes the reader assemble that picture in their head.
 *
 * Hand-authored SVG on one scale: the bars, the ticks, the price marker and
 * every label are placed by the same domain-to-pixel mapping, so nothing can
 * drift. When the price lies outside the simulated range the domain is widened
 * to include it — a marker pinned to the edge of a chart it has actually run
 * off would read as "just barely outside", which is the opposite of the truth.
 */

type Bin = { from: number; to: number; count: number };

type Props = {
  histogram: Bin[];
  percentiles: Record<string, number>;
  price?: number | null;
  baseCase?: number | null;
};

const W = 720;
const H = 260;
const PAD = { top: 18, right: 16, bottom: 34, left: 16 };

const fmt = (n: number) =>
  n >= 1000 ? Math.round(n).toLocaleString() : n.toFixed(n < 10 ? 2 : 0);

export function ValueDistribution({
  histogram,
  percentiles,
  price,
  baseCase,
}: Props) {
  const bins = histogram.filter(
    (b) => Number.isFinite(b.from) && Number.isFinite(b.to),
  );
  if (bins.length === 0) return null;

  const loBin = Math.min(...bins.map((b) => b.from));
  const hiBin = Math.max(...bins.map((b) => b.to));

  // The price joins the domain rather than being clamped into it. If it is off
  // the end, the chart has to show it off the end.
  const marks = [price, baseCase].filter(
    (v): v is number => typeof v === "number" && v > 0,
  );
  const lo = Math.min(loBin, ...marks);
  const hi = Math.max(hiBin, ...marks);
  const span = hi - lo || 1;

  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const x = (v: number) => PAD.left + ((v - lo) / span) * plotW;
  const peak = Math.max(...bins.map((b) => b.count)) || 1;
  const y = (c: number) => PAD.top + plotH - (c / peak) * plotH;

  const p50 = percentiles.p50;
  const priceX = typeof price === "number" && price > 0 ? x(price) : null;
  const inside = typeof price === "number" && price >= loBin && price <= hiBin;

  const label =
    typeof price === "number"
      ? inside
        ? `Today's price, ${fmt(price)}, falls inside the simulated range.`
        : `Today's price, ${fmt(price)}, falls outside every one of these draws.`
      : "No price to compare against.";

  return (
    <figure className="m-0 flex flex-col gap-xs">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`Distribution of value per share from ${fmt(lo)} to ${fmt(hi)}. Median ${fmt(p50 ?? 0)}. ${label}`}
          className="h-auto w-full min-w-[420px]"
          style={{ color: "var(--on-ground-faint)" }}
        >
          {/* The bars. `currentColor` at low alpha so the whole chart inherits
           * the theme's text colour rather than naming a grey twice. */}
          {bins.map((b, i) => {
            const bx = x(b.from);
            const bw = Math.max(x(b.to) - bx - 0.5, 0.5);
            const by = y(b.count);
            return (
              <rect
                key={i}
                x={bx}
                y={by}
                width={bw}
                height={PAD.top + plotH - by}
                fill="var(--cobalt)"
                opacity={0.42}
              />
            );
          })}

          {/* Median: the single most useful reference inside the mass. */}
          {typeof p50 === "number" && (
            <>
              <line
                x1={x(p50)}
                x2={x(p50)}
                y1={PAD.top}
                y2={PAD.top + plotH}
                stroke="var(--on-ground-soft)"
                strokeWidth={1}
                strokeDasharray="3 3"
              />
              <text
                x={x(p50)}
                y={PAD.top - 6}
                textAnchor="middle"
                fontSize={11}
                fill="var(--on-ground-soft)"
              >
                median {fmt(p50)}
              </text>
            </>
          )}

          {/* The price, which is the comparison the whole chart exists for, so
           * it is the one solid, full-height, coloured mark. */}
          {priceX != null && (
            <>
              <line
                x1={priceX}
                x2={priceX}
                y1={PAD.top - 2}
                y2={PAD.top + plotH}
                stroke="var(--oxide)"
                strokeWidth={2}
              />
              <text
                x={Math.min(Math.max(priceX, 40), W - 40)}
                y={H - PAD.bottom + 26}
                textAnchor="middle"
                fontSize={11}
                fill="var(--oxide)"
              >
                price {fmt(price!)}
              </text>
            </>
          )}

          {/* Baseline plus the domain ends, so every label names a value the
           * chart actually reaches. */}
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={PAD.top + plotH}
            y2={PAD.top + plotH}
            stroke="currentColor"
            strokeWidth={1}
          />
          <text
            x={PAD.left}
            y={H - PAD.bottom + 12}
            fontSize={11}
            fill="currentColor"
          >
            {fmt(lo)}
          </text>
          <text
            x={W - PAD.right}
            y={H - PAD.bottom + 12}
            textAnchor="end"
            fontSize={11}
            fill="currentColor"
          >
            {fmt(hi)}
          </text>
        </svg>
      </div>
      <figcaption className="max-w-[72ch] text-body-xs text-on-ink-faint">
        Value per share across the simulated draws. {label}
      </figcaption>
    </figure>
  );
}
