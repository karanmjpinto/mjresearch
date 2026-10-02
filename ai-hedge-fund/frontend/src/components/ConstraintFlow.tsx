import { useEffect, useMemo, useState } from "react";
import {
  api,
  type ConstraintFlowResponse,
  type FlowConstraint,
} from "@/lib/api";
import { useWidth } from "./FactorCharts";
import { InfoTip } from "./InfoTip";

/**
 * The constraint map as a flow — all named exposures, split by system, split
 * by chokepoint.
 *
 * A Sankey needs a quantity that conserves at every split, and the constraint
 * map has no money in it: nothing in the catalogue carries a dollar figure, and
 * inventing one so the picture could be denominated in currency is the exact
 * move the file's sourcing rule exists to forbid. What does conserve is the
 * count of listed companies named against each chokepoint, so that is the
 * width, and the caption says so rather than letting a reader assume dollars.
 *
 * Each system is ordered tightest first, which is what makes the chart worth
 * drawing: the ribbons get *thinner* as the constraints get tighter. The
 * hardest things to get around are the ones with the fewest listed ways to own
 * them. That is a fact about market structure the card list cannot show.
 *
 * Purity is drawn as density of the system's own colour rather than a fourth
 * hue — solid for a pure play, washed out for a minor one — so a terminal bar
 * reads as one constraint rather than a stacked chart of three.
 */

const SYSTEM_COLOR: Record<string, string> = {
  intelligence: "var(--cobalt)",
  power: "var(--cadmium)",
  motion: "var(--verdigris)",
};

/** Purest first, and the opacity each band is drawn at. */
const BANDS: Array<{ id: "pure" | "major" | "minor"; alpha: number }> = [
  { id: "pure", alpha: 1 },
  { id: "major", alpha: 0.58 },
  { id: "minor", alpha: 0.26 },
];

const GAP_TERMINAL = 9;
const BAR_W = 13;
/* The first terminal starts at y=0 and its label is centred on a bar that can
 * be twelve pixels tall, so without this the top label is clipped by the
 * viewBox. Padding the whole drawing is one number rather than a special case
 * for the first row. */
const PAD_TOP = 24;
const PAD_BOTTOM = 12;

type Placed = FlowConstraint & { y: number; h: number };

function ribbon(x0: number, y0: number, x1: number, y1: number, h: number) {
  const mx = x0 + (x1 - x0) / 2;
  return [
    `M ${x0} ${y0}`,
    `C ${mx} ${y0}, ${mx} ${y1}, ${x1} ${y1}`,
    `L ${x1} ${y1 + h}`,
    `C ${mx} ${y1 + h}, ${mx} ${y0 + h}, ${x0} ${y0 + h}`,
    "Z",
  ].join(" ");
}

export function ConstraintFlow() {
  const [data, setData] = useState<ConstraintFlowResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [box, width] = useWidth<HTMLDivElement>();

  useEffect(() => {
    let live = true;
    api
      .getConstraintFlow()
      .then((d) => live && setData(d))
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, []);

  const layout = useMemo(() => {
    if (!data || data.total === 0) return null;
    const terminals = data.systems.flatMap((s) => s.constraints);
    const height = Math.max(520, terminals.length * 56);
    const gaps = (terminals.length - 1) * GAP_TERMINAL;
    const unit = (height - gaps) / data.total;

    /* Terminals stack top to bottom in system order, tightest first inside
     * each system — the ordering is the argument, so it comes from the API
     * rather than being re-sorted here. */
    let y = PAD_TOP;
    const placed: Placed[] = [];
    for (const s of data.systems) {
      for (const c of s.constraints) {
        const h = c.value * unit;
        placed.push({ ...c, y, h });
        y += h + GAP_TERMINAL;
      }
    }

    const sysBlocks = data.systems.map((s) => {
      const mine = placed.filter((p) => p.system === s.id);
      const top = mine[0]!.y;
      const bottom = mine[mine.length - 1]!.y + mine[mine.length - 1]!.h;
      const h = s.value * unit;
      /* Centred on the span its constraints occupy, so the ribbons leaving it
       * fan out symmetrically instead of all bending one way. */
      return { ...s, h, y: top + (bottom - top) / 2 - h / 2 };
    });

    const rootH = data.total * unit;
    const rootY = PAD_TOP + height / 2 - rootH / 2;
    return { placed, sysBlocks, height, unit, rootH, rootY };
  }, [data]);

  if (error) {
    return (
      <div ref={box}>
        <p className="max-w-measure text-body-sm text-on-ink-soft">
          The flow could not be loaded: {error}
        </p>
      </div>
    );
  }
  if (!data || !layout) {
    return (
      <div ref={box}>
        <p className="text-body-sm text-on-ink-faint">
          Reading the constraint map…
        </p>
      </div>
    );
  }

  const w = Math.max(760, Math.min(width || 1120, 1180));
  const LABEL_W = 330;
  const xRoot = 0;
  const xSys = Math.max(170, (w - LABEL_W) * 0.26);
  const xTerm = w - LABEL_W;
  const { placed, sysBlocks, height, unit, rootH, rootY } = layout;

  /* Cumulative offsets: a ribbon leaves its source at the running total of
   * everything already drawn out of that node, which is what keeps the
   * widths honest where several ribbons share one node. */
  const sysOffset = new Map<string, number>();
  let rootOffset = 0;

  return (
    <div ref={box} className="flex flex-col gap-md">
      <div className="flex flex-wrap items-baseline justify-between gap-sm">
        <h3 className="flex items-center gap-xs font-display text-label uppercase tracking-label text-cadmium">
          Where the investable surface is
          <InfoTip term="constraint-flow" />
        </h3>
        <p className="text-body-xs text-on-ink-faint">
          {data.total} named exposures · width is companies, not money
        </p>
      </div>

      <svg
        width={w}
        height={height + PAD_TOP + PAD_BOTTOM}
        viewBox={`0 0 ${w} ${height + PAD_TOP + PAD_BOTTOM}`}
        className="block"
        role="img"
        aria-label={`Named exposures flowing from three systems out to ${placed.length} chokepoints, ordered tightest first`}
      >
        <title>
          {data.total} named exposures across {placed.length} chokepoints
        </title>

        {/* root → system */}
        {sysBlocks.map((s) => {
          const y0 = rootY + rootOffset;
          rootOffset += s.h;
          return (
            <path
              key={`r-${s.id}`}
              d={ribbon(xRoot + BAR_W, y0, xSys, s.y, s.h)}
              fill={SYSTEM_COLOR[s.id]}
              opacity={active ? 0.12 : 0.28}
            />
          );
        })}

        {/* system → chokepoint */}
        {placed.map((c) => {
          const s = sysBlocks.find((b) => b.id === c.system)!;
          const off = sysOffset.get(c.system) ?? 0;
          sysOffset.set(c.system, off + c.h);
          const on = active === c.id;
          return (
            <path
              key={`l-${c.id}`}
              d={ribbon(xSys + BAR_W, s.y + off, xTerm, c.y, c.h)}
              fill={SYSTEM_COLOR[c.system]}
              opacity={active ? (on ? 0.72 : 0.09) : 0.42}
              onMouseEnter={() => setActive(c.id)}
              onMouseLeave={() => setActive(null)}
              style={{ cursor: "pointer" }}
            />
          );
        })}

        {/* the root bar */}
        <rect
          x={xRoot}
          y={rootY}
          width={BAR_W}
          height={rootH}
          fill="var(--on-ink)"
        />
        <text
          x={xRoot}
          y={rootY - 14}
          fontSize={12}
          letterSpacing="0.1em"
          fill="var(--on-ink-faint)"
          className="uppercase"
        >
          All live chokepoints
        </text>

        {/* system bars */}
        {sysBlocks.map((s) => (
          <g key={s.id}>
            <rect
              x={xSys}
              y={s.y}
              width={BAR_W}
              height={s.h}
              fill={SYSTEM_COLOR[s.id]}
            />
            <text
              x={xSys + BAR_W + 10}
              y={s.y + 16}
              fontSize={12}
              letterSpacing="0.1em"
              fill="var(--on-ink-soft)"
              className="uppercase"
            >
              {s.label}
            </text>
            <text
              x={xSys + BAR_W + 10}
              y={s.y + 34}
              fontSize={12}
              fill="var(--on-ink-faint)"
            >
              {s.value}
            </text>
          </g>
        ))}

        {/* chokepoint terminals, each split by how pure the exposure is */}
        {placed.map((c) => {
          const on = active === c.id;
          let segY = c.y;
          return (
            <g
              key={c.id}
              onMouseEnter={() => setActive(c.id)}
              onMouseLeave={() => setActive(null)}
              style={{ cursor: "pointer" }}
            >
              {/* Three of the sixteen names are too long for the rail, so the
               * full text has to be recoverable rather than just cut. */}
              <title>
                {c.label} — {c.value} named{" "}
                {c.value === 1 ? "company" : "companies"}
                {c.tightness !== null
                  ? `, ${c.tightness.toFixed(2)}× normal`
                  : ", not measured against a normal"}
              </title>
              {BANDS.map((b) => {
                const n = c.bands[b.id];
                if (!n) return null;
                const h = n * unit;
                const y = segY;
                segY += h;
                return (
                  <rect
                    key={b.id}
                    x={xTerm}
                    y={y}
                    width={BAR_W}
                    height={h}
                    fill={SYSTEM_COLOR[c.system]}
                    opacity={b.alpha}
                  />
                );
              })}
              <text
                x={xTerm + BAR_W + 12}
                y={c.y + c.h / 2 - 2}
                fontSize={13}
                fill={on ? "var(--bone)" : "var(--on-ink)"}
              >
                {c.label.length > 34 ? `${c.label.slice(0, 33)}…` : c.label}
              </text>
              <text
                x={xTerm + BAR_W + 12}
                y={c.y + c.h / 2 + 15}
                fontSize={12}
                fill="var(--on-ink-faint)"
                className="tabular"
              >
                {c.value} {c.value === 1 ? "name" : "names"}
                {c.tightness !== null
                  ? ` · ${c.tightness.toFixed(2)}× normal`
                  : ""}
              </text>
            </g>
          );
        })}
      </svg>

      {/* The same figures as the drawing, for a reader who cannot use it.
       * The SVG stays one labelled image: making sixteen <g>s tabbable would
       * add sixteen stops that only repeat these rows. */}
      <table className="sr-only">
        <caption>
          Named exposures per chokepoint, each system ordered tightest first
        </caption>
        <thead>
          <tr>
            <th scope="col">Chokepoint</th>
            <th scope="col">System</th>
            <th scope="col">Named companies</th>
            <th scope="col">Pure</th>
            <th scope="col">Major</th>
            <th scope="col">Minor</th>
            <th scope="col">Tightness</th>
          </tr>
        </thead>
        <tbody>
          {placed.map((c) => (
            <tr key={c.id}>
              <th scope="row">{c.label}</th>
              <td>{c.system}</td>
              <td>{c.value}</td>
              <td>{c.bands.pure}</td>
              <td>{c.bands.major}</td>
              <td>{c.bands.minor}</td>
              <td>
                {c.tightness !== null
                  ? `${c.tightness.toFixed(2)}× normal`
                  : "not measured"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex flex-wrap items-center gap-lg">
        <div className="flex items-center gap-sm">
          {BANDS.map((b) => (
            <span
              key={b.id}
              className="flex items-center gap-2xs text-body-xs text-on-ink-faint"
            >
              <span
                aria-hidden="true"
                className="inline-block h-3 w-3"
                style={{ background: "var(--on-ink)", opacity: b.alpha }}
              />
              {b.id}
            </span>
          ))}
        </div>
        <p className="max-w-measure text-body-xs text-on-ink-faint">
          {data.note}
        </p>
      </div>
    </div>
  );
}
