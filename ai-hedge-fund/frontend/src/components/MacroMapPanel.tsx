import { useEffect, useMemo, useState } from "react";
import { api, type MacroMapResponse, type MacroPoint } from "@/lib/api";
import { useWidth } from "./FactorCharts";
import { InfoTip } from "./InfoTip";

/**
 * The growth/inflation map — AQR's Exhibit 4, on the data this repo can source.
 *
 * Each point is a return series placed by two partial correlations: how its
 * twelve-month returns have moved with US inflation news, holding growth news
 * fixed, and with growth news holding inflation fixed. The quadrant names
 * describe the *environment*, not the asset — a series in "stagflation" is one
 * whose good years have been the ones with rising inflation and falling growth.
 *
 * Two deliberate departures from the exhibit it copies.
 *
 * Only the anchors and the company are labelled on the chart. Twenty-seven
 * labels on one square either collide or get placed by a heuristic that lies
 * about position; the table carries every name, and hovering either side lights
 * the other.
 *
 * The error bar is drawn, not buried. These are overlapping twelve-month
 * windows read off quarterly, so half a century supplies about fifty
 * independent observations and every point carries a standard error near 0.14.
 * Drawing that as a ring is the difference between a map you read by quadrant
 * and one you read to two decimal places.
 */

const LIM = 0.6;

const KIND_LABEL: Record<MacroPoint["kind"], string> = {
  anchor: "Market and bonds",
  industry: "Industries",
  factor: "Factor themes",
  company: "This company",
};

const KIND_COLOR: Record<MacroPoint["kind"], string> = {
  anchor: "var(--on-ground)",
  industry: "var(--verdigris)",
  factor: "var(--cobalt)",
  company: "var(--oxide)",
};

/** Marker radius, and whether it is drawn hollow. The chart and the group
 * headings read from the same table, so a heading is never distinguished by
 * colour alone: a reader who cannot separate the hues still has the ring
 * against the disc, and the disc's size. */
const KIND_MARK: Record<MacroPoint["kind"], { r: number; hollow: boolean }> = {
  anchor: { r: 5.5, hollow: false },
  industry: { r: 4.5, hollow: true },
  factor: { r: 4.5, hollow: false },
  company: { r: 7, hollow: false },
};

function Marker({ kind }: { kind: MacroPoint["kind"] }) {
  const { r, hollow } = KIND_MARK[kind];
  const colour = KIND_COLOR[kind];
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 16 16"
      aria-hidden="true"
      className="shrink-0"
    >
      <circle
        cx={8}
        cy={8}
        r={r}
        fill={hollow ? "var(--ground)" : colour}
        stroke={colour}
        strokeWidth={hollow ? 2 : 0}
      />
    </svg>
  );
}

const QUADRANTS = [
  {
    id: "goldilocks",
    label: "Goldilocks",
    x: -LIM,
    y: LIM,
    tint: "var(--verdigris)",
  },
  {
    id: "overheating",
    label: "Overheating",
    x: 0,
    y: LIM,
    tint: "var(--cadmium)",
  },
  { id: "recession", label: "Recession", x: -LIM, y: 0, tint: "var(--cobalt)" },
  { id: "stagflation", label: "Stagflation", x: 0, y: 0, tint: "var(--oxide)" },
] as const;

function fmt(v: number) {
  return v.toFixed(2).replace("-", "−");
}

// ── the chart ──────────────────────────────────────────────────────────────

function Scatter({
  points,
  active,
  onActive,
  width,
}: {
  points: MacroPoint[];
  active: string | null;
  onActive: (id: string | null) => void;
  width: number;
}) {
  const pad = { l: 44, r: 16, t: 16, b: 40 };
  const side = Math.max(280, Math.min(width, 620));
  const plot = side - pad.l - pad.r;
  const X = (v: number) => pad.l + ((v + LIM) / (2 * LIM)) * plot;
  const Y = (v: number) => pad.t + ((LIM - v) / (2 * LIM)) * plot;
  const height = plot + pad.t + pad.b;
  const ticks = [-0.6, -0.3, 0, 0.3, 0.6];

  const shown = points.find((p) => p.id === active) ?? null;

  return (
    <svg
      width={side}
      height={height}
      className="block text-on-ground-faint"
      role="img"
      aria-label="Growth sensitivity against inflation sensitivity, four macro quadrants"
    >
      {QUADRANTS.map((q) => (
        <rect
          key={q.id}
          x={X(q.x)}
          y={Y(q.y)}
          width={plot / 2}
          height={plot / 2}
          fill={`color-mix(in oklch, ${q.tint} 7%, transparent)`}
        />
      ))}

      {ticks.map((t) => (
        <g key={t}>
          <line
            x1={X(t)}
            y1={Y(LIM)}
            x2={X(t)}
            y2={Y(-LIM)}
            stroke="var(--ground-line)"
          />
          <line
            x1={X(-LIM)}
            y1={Y(t)}
            x2={X(LIM)}
            y2={Y(t)}
            stroke="var(--ground-line)"
          />
          <text
            x={X(t)}
            y={Y(-LIM) + 16}
            textAnchor="middle"
            fontSize={12}
            fill="currentColor"
          >
            {fmt(t)}
          </text>
          <text
            x={pad.l - 8}
            y={Y(t) + 4}
            textAnchor="end"
            fontSize={12}
            fill="currentColor"
          >
            {fmt(t)}
          </text>
        </g>
      ))}

      <line
        x1={X(0)}
        y1={Y(LIM)}
        x2={X(0)}
        y2={Y(-LIM)}
        stroke="var(--on-ground)"
        strokeWidth={1}
      />
      <line
        x1={X(-LIM)}
        y1={Y(0)}
        x2={X(LIM)}
        y2={Y(0)}
        stroke="var(--on-ground)"
        strokeWidth={1}
      />

      {QUADRANTS.map((q) => (
        <text
          key={q.id}
          x={q.x < 0 ? X(-LIM) + 8 : X(LIM) - 8}
          y={q.y > 0 ? Y(LIM) + 16 : Y(-LIM) - 8}
          textAnchor={q.x < 0 ? "start" : "end"}
          fontSize={12}
          letterSpacing="0.1em"
          fill="currentColor"
          className="uppercase"
        >
          {q.label}
        </text>
      ))}

      {points.map((p) => {
        const on = p.id === active;
        const colour = KIND_COLOR[p.kind];
        const mark = KIND_MARK[p.kind];
        return (
          <g
            key={p.id}
            onMouseEnter={() => onActive(p.id)}
            onMouseLeave={() => onActive(null)}
            style={{ cursor: "pointer" }}
          >
            {/* The uncertainty, drawn once for whatever is being read. */}
            {on && (
              <circle
                cx={X(p.inflation)}
                cy={Y(p.growth)}
                r={(p.standard_error / (2 * LIM)) * plot}
                fill={`color-mix(in oklch, ${colour} 12%, transparent)`}
                stroke={colour}
                strokeDasharray="3 3"
                strokeWidth={1}
              />
            )}
            <circle
              cx={X(p.inflation)}
              cy={Y(p.growth)}
              r={mark.r}
              fill={mark.hollow ? "var(--ground)" : colour}
              stroke={colour}
              strokeWidth={mark.hollow ? 2 : on ? 2 : 0}
            />
          </g>
        );
      })}

      {/* Labelled always: the three anchors and the company. Everything else
       * is named in the table, and on the chart only while it is being read. */}
      {points
        .filter(
          (p) => p.kind === "anchor" || p.kind === "company" || p.id === active,
        )
        .map((p) => (
          <text
            key={`l-${p.id}`}
            x={X(p.inflation)}
            y={Y(p.growth) - (p.kind === "company" ? 13 : 11)}
            textAnchor="middle"
            fontSize={12}
            fill={p.id === active ? "var(--strong)" : "var(--on-ground-soft)"}
            style={{
              paintOrder: "stroke",
              stroke: "var(--ground)",
              strokeWidth: 3,
            }}
          >
            {p.label}
          </text>
        ))}

      <text
        x={pad.l + plot / 2}
        y={height - 8}
        textAnchor="middle"
        fontSize={12}
        fill="var(--on-ground-soft)"
      >
        Inflation sensitivity
        {shown ? ` · ${shown.label} ${fmt(shown.inflation)}` : ""}
      </text>
      <text
        transform={`translate(12, ${pad.t + plot / 2}) rotate(-90)`}
        textAnchor="middle"
        fontSize={12}
        fill="var(--on-ground-soft)"
      >
        Growth sensitivity{shown ? ` · ${fmt(shown.growth)}` : ""}
      </text>
    </svg>
  );
}

// ── the panel ──────────────────────────────────────────────────────────────

export function MacroMapPanel({ ticker }: { ticker: string }) {
  const [data, setData] = useState<MacroMapResponse | null>(null);
  const [company, setCompany] = useState<MacroPoint | null>(null);
  const [tooShort, setTooShort] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [box, width] = useWidth<HTMLDivElement>();

  useEffect(() => {
    let live = true;
    api
      .getMacroMap()
      .then((d) => live && setData(d))
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    if (!ticker) return;
    let live = true;
    setCompany(null);
    setTooShort(null);
    api
      .getMacroPoint(ticker)
      .then((d) => {
        if (!live) return;
        setCompany(d.point);
        setTooShort(d.point ? null : d.reason);
      })
      .catch(() => live && setTooShort("no price history for this ticker"));
    return () => {
      live = false;
    };
  }, [ticker]);

  const points = useMemo(() => {
    const base = data?.points ?? [];
    return company ? [...base, company] : base;
  }, [data, company]);

  const grouped = useMemo(() => {
    const order: MacroPoint["kind"][] = [
      "company",
      "anchor",
      "industry",
      "factor",
    ];
    return order
      .map((kind) => ({
        kind,
        rows: points
          .filter((p) => p.kind === kind)
          .sort((a, b) => a.inflation - b.inflation),
      }))
      .filter((g) => g.rows.length > 0);
  }, [points]);

  const ctx = data?.context ?? null;
  const built = ctx?.built_at.slice(0, 10) ?? "";
  const span = ctx
    ? `${ctx.quarters[0]}–${ctx.quarters[ctx.quarters.length - 1]}`
    : "";

  // One wrapper, measured, that outlives every state this panel has. Swapping
  // the measured element between loading and loaded would leave the
  // ResizeObserver watching a node React had already detached, and the chart
  // would sit at its minimum size for the life of the page.
  return (
    <div ref={box} className="flex flex-col gap-lg">
      {error && (
        <p className="max-w-measure text-body-sm text-on-ground-soft">
          The map could not be loaded: {error}
        </p>
      )}
      {!error && !ctx && (
        <p className="text-body-sm text-on-ground-faint">
          Reading the macro series…
        </p>
      )}
      {ctx && (
        <>
          <div className="flex flex-wrap items-start gap-lg">
            <Scatter
              points={points}
              active={active}
              onActive={setActive}
              width={width}
            />

            <div className="flex min-w-[15rem] flex-1 flex-col gap-sm">
              <p className="max-w-measure text-body-sm text-on-ground-soft">
                Where each series has earned its returns: to the right when
                inflation news surprised upwards, above the line when growth
                news did. <InfoTip term="macro-sensitivity" />
              </p>
              <dl className="flex flex-col gap-2xs text-body-xs text-on-ground-faint">
                <div className="flex gap-xs">
                  <dt className="w-24 shrink-0">Sample</dt>
                  <dd className="text-on-ground-soft">{span}, quarterly</dd>
                </div>
                <div className="flex gap-xs">
                  <dt className="w-24 shrink-0">Error bar</dt>
                  <dd className="text-on-ground-soft">
                    about ±0.14 on a full sample — read the quadrant, not the
                    decimal
                  </dd>
                </div>
                <div className="flex gap-xs">
                  <dt className="w-24 shrink-0">Built</dt>
                  <dd className="text-on-ground-soft">{built}</dd>
                </div>
              </dl>
              {tooShort && (
                <p className="max-w-measure text-body-xs text-on-ground-faint">
                  {ticker} is not on the map: {tooShort}.
                </p>
              )}
            </div>
          </div>

          <div className="flex flex-wrap gap-lg">
            {grouped.map((group) => (
              <div key={group.kind} className="min-w-[16rem] flex-1">
                <h3 className="mb-xs flex items-center gap-xs text-label uppercase tracking-label text-on-ground-faint">
                  <Marker kind={group.kind} />
                  {KIND_LABEL[group.kind]}
                </h3>
                <table className="w-full text-body-xs">
                  <thead className="text-on-ground-faint">
                    <tr>
                      <th scope="col" className="py-2xs text-left font-normal">
                        Series
                      </th>
                      <th scope="col" className="py-2xs text-right font-normal">
                        Infl.
                      </th>
                      <th scope="col" className="py-2xs text-right font-normal">
                        Growth
                      </th>
                      <th scope="col" className="py-2xs text-right font-normal">
                        Years
                      </th>
                    </tr>
                  </thead>
                  {/* Focusable rows, not focusable dots. The chart is one
                   * labelled image; making twenty-seven <g>s tabbable would
                   * add twenty-seven stops that only repeat these cells. This
                   * way a keyboard reader gets the same highlight a pointer
                   * does, and the numbers are in the row either way. */}
                  <tbody>
                    {group.rows.map((p) => (
                      <tr
                        key={p.id}
                        tabIndex={0}
                        onMouseEnter={() => setActive(p.id)}
                        onMouseLeave={() => setActive(null)}
                        onFocus={() => setActive(p.id)}
                        onBlur={() => setActive(null)}
                        className={
                          p.id === active
                            ? "bg-ground-raised text-strong"
                            : "text-on-ground-soft"
                        }
                      >
                        <th
                          scope="row"
                          className="py-2xs pr-xs text-left font-normal"
                        >
                          {p.label}
                        </th>
                        <td className="tabular py-2xs text-right">
                          {fmt(p.inflation)}
                        </td>
                        <td className="tabular py-2xs text-right">
                          {fmt(p.growth)}
                        </td>
                        <td className="tabular py-2xs text-right text-on-ground-faint">
                          {p.independent_years.toFixed(0)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>

          <div className="flex max-w-measure flex-col gap-xs text-body-xs text-on-ground-faint">
            <p>
              Method from AQR, <i>Alternative Thinking</i> 2026 Issue 3. Each
              macro metric is an equal-risk blend of the twelve-month change in
              the rate and the twelve-month surprise against forecasts; a point
              is the partial correlation of a series&rsquo; twelve-month returns
              to one metric holding the other fixed.
            </p>
            {ctx.inflation.forecast_splice && (
              <p>{ctx.inflation.forecast_splice}</p>
            )}
            <p>{ctx.absent}</p>
            <p>
              Sources: {ctx.source.realised} {ctx.source.forecasts}{" "}
              {ctx.source.returns} Factor themes are the JKP series behind the
              Factors tab.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
