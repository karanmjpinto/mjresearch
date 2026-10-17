import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type ScreenRow } from "@/lib/api";

/**
 * Cambrian Capital's AI supply-chain thesis, as charts beside the screen.
 *
 * Two kinds of figure sit on this panel and the panel says which is which on
 * every one, because that is this app's whole argument:
 *
 *   computed   the revenue-multiples dot plot and the torque calculator. The
 *              dots are this desk's own screen run, so they move when the
 *              market does and can be re-derived.
 *   estimate   supply growth, buyer price sensitivity and the five worlds.
 *              These are Cambrian's numbers as published in September 2026,
 *              copied rather than computed, and the panel cannot check them.
 *
 * On linen rather than ink: DESIGN.md keeps the canvas ground for print-like
 * reading surfaces, and a thesis read top to bottom is one.
 */

const SOURCE = "https://cambrianmanagement.ai/#thesis";

type Segment = { id: string; label: string; physical: boolean };

const SEGMENTS: readonly Segment[] = [
  { id: "wafers", label: "Silicon wafers", physical: true },
  { id: "memory", label: "Memory", physical: true },
  { id: "capacitors", label: "Capacitors", physical: true },
  { id: "foundries", label: "Chip factories", physical: true },
  { id: "fabless", label: "Fabless chips", physical: false },
  { id: "software", label: "Large software", physical: false },
];

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function median(xs: number[]): number | null {
  if (xs.length === 0) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2;
}

type Kind = "computed" | "estimate" | "view";

const KIND_LABEL: Record<Kind, string> = {
  computed: "Computed here",
  estimate: "Cambrian's estimate",
  view: "This desk's view",
};

function Trust({ kind }: { kind: Kind }) {
  return (
    <span
      className={`font-display text-label uppercase tracking-label ${
        kind === "computed"
          ? "text-verdigris-paper"
          : kind === "estimate"
            ? "text-cadmium-paper"
            : "text-cobalt-paper"
      }`}
    >
      {KIND_LABEL[kind]}
    </span>
  );
}

function Figure({
  title,
  kind,
  children,
  note,
}: {
  title: string;
  kind: Kind;
  children: React.ReactNode;
  note?: string;
}) {
  return (
    <figure className="flex min-w-0 flex-col gap-sm rounded-lg border border-on-canvas/15 bg-paper/40 p-md">
      <div className="flex flex-wrap items-baseline justify-between gap-xs">
        <h3 className="font-display text-title-xs text-on-canvas">{title}</h3>
        <Trust kind={kind} />
      </div>
      {children}
      {note && (
        <figcaption className="text-body-xs text-on-canvas-faint">{note}</figcaption>
      )}
    </figure>
  );
}

// ── 1. Revenue multiples by segment (live) ──────────────────────────────

/** Top of the axis. Nothing in the run is above it; a dot that is clamps. */
const CAP = 64;

type Dot = { ticker: string; name: string; seg: string; x: number; passed: boolean };

function SegmentMultiples() {
  const q = useQuery({
    queryKey: ["screen-results", "cambrian-scarcity", "ai_supply_chain", "all"],
    queryFn: () =>
      api.getScreenResults("cambrian-scarcity", {
        universe: "ai_supply_chain",
        limit: 200,
        passingOnly: false,
      }),
    retry: false,
    staleTime: 5 * 60_000,
  });

  const dots = useMemo<Dot[]>(() => {
    const d = q.data;
    if (!d?.available) return [];
    const out: Dot[] = [];
    for (const r of d.results as ScreenRow[]) {
      const s = (r.snapshot ?? {}) as Record<string, unknown>;
      const x = num(s.revenue_multiple);
      const seg = typeof s.segment === "string" ? s.segment : null;
      if (x === null || !seg) continue; // a missing multiple is not a zero
      out.push({
        ticker: String(r.ticker ?? "?"),
        name: String(s.name ?? r.ticker ?? ""),
        seg,
        x,
        passed: r.passed === true,
      });
    }
    return out;
  }, [q.data]);

  if (q.isLoading) {
    return <p className="text-body-sm text-on-canvas-soft">Loading the screen run…</p>;
  }
  if (!q.data?.available || dots.length === 0) {
    return (
      <p className="text-body-sm text-on-canvas-soft">
        No run on the AI supply-chain universe yet. Build it with{" "}
        <code className="font-mono text-on-canvas">
          uv run python scripts/refresh_screens.py --screen cambrian-scarcity
        </code>
        .
      </p>
    );
  }

  const W = 760;
  const H = 380;
  const M = { t: 24, r: 12, b: 64, l: 48 };
  const ih = H - M.t - M.b;
  const colW = (W - M.l - M.r) / SEGMENTS.length;
  /* Log, not linear. The thesis is a ratio between segments — 2x against 30x
   * — and on a linear axis every hardware segment shares the bottom tenth of
   * the chart. Equal steps here are equal multiples. */
  const LO = 0.5;
  const y = (v: number) =>
    M.t + ih * (1 - Math.log(Math.min(Math.max(v, LO), CAP) / LO) / Math.log(CAP / LO));
  const ticks = [0.5, 1, 2, 4, 8, 16, 32, CAP];

  const medians = SEGMENTS.map((s) => ({
    seg: s,
    m: median(dots.filter((d) => d.seg === s.id).map((d) => d.x)),
    n: dots.filter((d) => d.seg === s.id).length,
  }));

  const summary = medians
    .filter((m) => m.m !== null)
    .map((m) => `${m.seg.label} median ${m.m!.toFixed(1)}x`)
    .join(", ");

  return (
    <>
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-auto w-full min-w-[640px]"
          role="img"
          aria-label={`Market cap over forward revenue by segment, log scale. ${summary}.`}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line
                x1={M.l}
                x2={W - M.r}
                y1={y(t)}
                y2={y(t)}
                stroke="var(--on-canvas)"
                strokeOpacity={t === CAP ? 0.35 : 0.12}
                strokeDasharray={t === CAP ? "4 4" : undefined}
              />
              <text
                x={M.l - 6}
                y={y(t) + 4}
                textAnchor="end"
                fontSize="13"
                fill="var(--on-canvas-faint)"
              >
                {t === CAP ? `${CAP}×+` : `${t}×`}
              </text>
            </g>
          ))}

          {medians.map(({ seg, m, n }, i) => {
            const cx = M.l + colW * i + colW / 2;
            const hue = seg.physical ? "var(--verdigris-paper)" : "var(--oxide-paper)";
            const segDots = dots.filter((d) => d.seg === seg.id).sort((a, b) => a.x - b.x);
            return (
              <g key={seg.id}>
                {m !== null && (
                  <>
                    <line
                      x1={cx - colW * 0.42}
                      x2={cx + colW * 0.42}
                      y1={y(m)}
                      y2={y(m)}
                      stroke={hue}
                      strokeWidth={4}
                    />
                    <text
                      x={cx - colW * 0.42}
                      y={y(m) - 8}
                      fontSize="16"
                      fontWeight={700}
                      fill={hue}
                    >
                      {m.toFixed(1)}×
                    </text>
                  </>
                )}
                {segDots.map((d, j) => {
                  // Three columns, filled in value order, so ties stay visible.
                  const dx = cx + colW * 0.12 + (j % 3) * 12;
                  return (
                    <circle
                      key={d.ticker}
                      cx={dx}
                      cy={y(d.x)}
                      r={5}
                      fill={hue}
                      fillOpacity={d.passed || !seg.physical ? 1 : 0.3}
                      stroke={hue}
                    >
                      <title>{`${d.name} (${d.ticker}) ${d.x.toFixed(1)}×${
                        seg.physical && !d.passed ? ", failed the screen" : ""
                      }`}</title>
                    </circle>
                  );
                })}
                <text
                  x={cx}
                  y={H - M.b + 22}
                  textAnchor="middle"
                  fontSize="14"
                  fontWeight={600}
                  fill="var(--on-canvas)"
                >
                  {seg.label}
                </text>
                <text
                  x={cx}
                  y={H - M.b + 38}
                  textAnchor="middle"
                  fontSize="13"
                  fill="var(--on-canvas-faint)"
                >
                  {n} listed
                </text>
              </g>
            );
          })}

          <text x={M.l} y={H - 6} fontSize="13" fill="var(--verdigris-paper)" fontWeight={600}>
            AI HARDWARE SUPPLY CHAIN, OWNS PLANT
          </text>
          <text
            x={W - M.r}
            y={H - 6}
            textAnchor="end"
            fontSize="13"
            fill="var(--oxide-paper)"
            fontWeight={600}
          >
            NO FACTORIES — CONTRAST
          </text>
        </svg>
      </div>
      <p className="text-body-xs text-on-canvas-faint">
        Market cap ÷ next-twelve-month consensus revenue, on a log scale, from this desk's run
        built {new Date(q.data.built_at).toLocaleDateString()}. Each dot is one company; the line
        is the segment median. A pale dot failed the screen. Hover a dot for the name.
      </p>
    </>
  );
}

// ── 2. Supply growth to 2030 (Cambrian) ─────────────────────────────────

const SUPPLY = [
  { label: "DRAM bits", g: 0.23, hue: "var(--cobalt-paper)" },
  { label: "NAND bits", g: 0.19, hue: "var(--verdigris-paper)" },
  { label: "High-end MLCCs", g: 0.13, hue: "var(--cadmium-paper)" },
  { label: "Leading-edge wafers", g: 0.09, hue: "var(--oxide-paper)" },
] as const;

function SupplyGrowth() {
  const W = 420;
  const H = 240;
  const M = { t: 12, r: 150, b: 28, l: 36 };
  const years = [2026, 2027, 2028, 2029, 2030];
  const x = (i: number) => M.l + ((W - M.l - M.r) * i) / (years.length - 1);
  const y = (v: number) => M.t + (H - M.t - M.b) * (1 - (v - 1) / 1.5);
  return (
    <div className="overflow-x-auto">
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full min-w-[420px]"
      role="img"
      aria-label="Supply indexed to 2026. By 2030 DRAM bits 2.3x, NAND 2.0x, high-end MLCCs 1.6x, leading-edge wafers 1.4x."
    >
      {[1, 1.5, 2, 2.5].map((t) => (
        <g key={t}>
          <line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} stroke="var(--on-canvas)" strokeOpacity={0.12} />
          <text x={M.l - 6} y={y(t) + 4} textAnchor="end" fontSize="12" fill="var(--on-canvas-faint)">
            {t}×
          </text>
        </g>
      ))}
      {years.map((yr, i) => (
        <text key={yr} x={x(i)} y={H - 8} textAnchor="middle" fontSize="12" fill="var(--on-canvas-faint)">
          {i === 0 || i === years.length - 1 ? yr : `’${String(yr).slice(2)}`}
        </text>
      ))}
      {SUPPLY.map((s) => {
        const pts = years.map((_, i) => `${x(i)},${y((1 + s.g) ** i)}`).join(" ");
        const end = (1 + s.g) ** (years.length - 1);
        return (
          <g key={s.label}>
            <polyline points={pts} fill="none" stroke={s.hue} strokeWidth={3} />
            <text x={W - M.r + 8} y={y(end) + 4} fontSize="12" fill={s.hue} fontWeight={600}>
              {`${end.toFixed(1)}× ${s.label}`}
            </text>
          </g>
        );
      })}
    </svg>
    </div>
  );
}

// ── 3. Operating leverage (computed) ────────────────────────────────────

function Slider({
  label,
  value,
  min,
  max,
  onChange,
  suffix,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
  suffix: string;
}) {
  return (
    <label className="flex flex-col gap-2xs text-body-xs text-on-canvas-soft">
      <span className="flex justify-between">
        <span>{label}</span>
        <span className="font-display tabular text-on-canvas">
          {value > 0 && suffix === "%" && label.startsWith("Volume") ? "+" : ""}
          {value}
          {suffix}
        </span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="accent-[var(--verdigris-paper)]"
      />
    </label>
  );
}

function TorqueCalculator() {
  const [fixed, setFixed] = useState(55);
  const [variable, setVariable] = useState(30);
  const [volume, setVolume] = useState(10);
  const profit = 100 - fixed - variable;
  const newProfit = 100 * (1 + volume / 100) - fixed - variable * (1 + volume / 100);
  const change = profit > 0 ? (newProfit / profit - 1) * 100 : null;
  const dol = profit > 0 ? (100 - variable) / profit : null;
  return (
    <div className="flex flex-col gap-sm">
      <p className="text-body-xs text-on-canvas-soft">
        Revenue of 100, prices flat. Fixed cost does not move with volume, so a plant that is
        mostly paid for turns a small volume change into a large profit change.
      </p>
      <Slider label="Fixed cost" value={fixed} min={0} max={95 - variable} onChange={setFixed} suffix="" />
      <Slider label="Variable cost" value={variable} min={0} max={95 - fixed} onChange={setVariable} suffix="" />
      <Slider label="Volume change" value={volume} min={-20} max={30} onChange={setVolume} suffix="%" />
      <div className="flex flex-wrap items-baseline gap-md border-t border-on-canvas/15 pt-sm">
        <p className="font-display text-display-sm tabular text-verdigris-paper">
          {change === null ? "—" : `${change >= 0 ? "+" : ""}${change.toFixed(0)}%`}
        </p>
        <p className="text-body-xs text-on-canvas-soft">
          profit change, from a profit of {profit}.{" "}
          {dol !== null && (
            <>
              Operating leverage {dol.toFixed(1)}× — the screen computes the same ratio from
              each company's statements.
            </>
          )}
        </p>
      </div>
    </div>
  );
}

// ── 4. Who cuts volume first (Cambrian) ─────────────────────────────────

type Buyer = { who: string; input: string; margin: string; trigger: string; share: string; elastic: boolean };

const MEMORY_BUYERS: readonly Buyer[] = [
  { who: "Nvidia (HBM)", input: "~12%", margin: "~60%", trigger: "+200%", share: "~10%", elastic: false },
  { who: "Hyperscaler servers", input: "~12%", margin: "~35%", trigger: "+115%", share: "~25%", elastic: false },
  { who: "Apple", input: "~6%", margin: "~30%", trigger: "+200%", share: "~10%", elastic: false },
  { who: "Android mid/low OEMs", input: "~12%", margin: "~4%", trigger: "+13%", share: "~25%", elastic: true },
  { who: "PC OEMs", input: "~12%", margin: "~5%", trigger: "+17%", share: "~15%", elastic: true },
  { who: "Consumer/other", input: "~10%", margin: "~5%", trigger: "+20%", share: "~15%", elastic: true },
];

const WAFER_BUYERS: readonly Buyer[] = [
  { who: "TSMC leading edge", input: "~1%", margin: "~45%", trigger: "+1,800%", share: "~23%", elastic: false },
  { who: "DRAM/HBM makers", input: "~1%", margin: "~50–75%", trigger: "+2,000%", share: "~28%", elastic: false },
  { who: "NAND makers", input: "~2–3%", margin: "~30%", trigger: "+450%", share: "~20%", elastic: false },
  { who: "Mature foundries", input: "~3%", margin: "~20%", trigger: "+270%", share: "~15%", elastic: false },
  { who: "Image sensors", input: "~3%", margin: "~18%", trigger: "+240%", share: "~7%", elastic: false },
  { who: "Power/analog", input: "~10–20%", margin: "~25%", trigger: "+50–140%", share: "~5%", elastic: true },
];

function BuyerTable({ title, verdict, rows }: { title: string; verdict: string; rows: readonly Buyer[] }) {
  return (
    <div className="min-w-0">
      <p className="flex flex-wrap items-baseline justify-between gap-xs">
        <span className="font-display text-body-sm text-on-canvas">{title}</span>
        <span className="text-body-xs font-semibold text-oxide-paper">{verdict}</span>
      </p>
      <div className="overflow-x-auto">
        <table className="mt-xs w-full min-w-[26rem] text-left text-body-xs">
          <thead>
            <tr className="border-b border-on-canvas/40 font-display text-label uppercase tracking-label text-on-canvas-faint">
              <th className="py-2xs pr-sm font-normal">Buyer</th>
              <th className="py-2xs pr-sm text-right font-normal">Input % of cost</th>
              <th className="py-2xs pr-sm text-right font-normal">Op margin</th>
              <th className="py-2xs pr-sm text-right font-normal">Cuts at</th>
              <th className="py-2xs text-right font-normal">Of demand</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((b) => (
              <tr
                key={b.who}
                className={`border-b border-on-canvas/10 ${b.elastic ? "font-semibold text-oxide-paper" : "text-on-canvas"}`}
              >
                <td className="py-2xs pr-sm">
                  {b.who}
                  {b.elastic && <span className="sr-only"> (price sensitive)</span>}
                </td>
                <td className="py-2xs pr-sm text-right tabular">{b.input}</td>
                <td className="py-2xs pr-sm text-right tabular">{b.margin}</td>
                <td className="py-2xs pr-sm text-right tabular">{b.trigger}</td>
                <td className="py-2xs text-right tabular">{b.share}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── 5. Five worlds (Cambrian) ───────────────────────────────────────────

const WORLDS = [
  { world: "US labs keep durable moats", why: "the one world both bets need", lab: true },
  { world: "Heavy government involvement", why: "state labs still buy every input", lab: false },
  { world: "Open-weight models close the gap", why: "cheaper models, far more inference", lab: false },
  { world: "Chinese labs catch up", why: "scarcity falls, compute demand does not", lab: false },
  { world: "A price war crushes lab margins", why: "labs buy more compute to keep up", lab: false },
] as const;

function FiveWorlds() {
  const mark = (yes: boolean) =>
    yes ? (
      <span className="text-verdigris-paper" role="img" aria-label="wins">
        ✓
      </span>
    ) : (
      <span className="text-on-canvas-faint" role="img" aria-label="does not win">
        –
      </span>
    );
  return (
    <table className="w-full text-left text-body-xs">
      <thead>
        <tr className="border-b border-on-canvas/40 font-display text-label uppercase tracking-label text-on-canvas-faint">
          <th className="py-2xs pr-sm font-normal">World</th>
          <th className="py-2xs pr-sm text-center font-normal">Lab equity</th>
          <th className="py-2xs text-center font-normal">AI infra</th>
        </tr>
      </thead>
      <tbody>
        {WORLDS.map((w) => (
          <tr key={w.world} className="border-b border-on-canvas/10">
            <td className="py-xs pr-sm">
              <span className="block text-on-canvas">{w.world}</span>
              <span className="block text-on-canvas-faint">{w.why}</span>
            </td>
            <td className="py-xs pr-sm text-center text-body-lg">{mark(w.lab)}</td>
            <td className="py-xs text-center text-body-lg">{mark(true)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── The panel ───────────────────────────────────────────────────────────

const CHAIN = [
  "As compute gets more valuable, value flows to the scarce physical inputs that make it.",
  "Software is automated before factories are, so own plant and process know-how, not fabless designers.",
  "Idle capacity, low utilisation and low margins are torque in a fast-AI world, so read revenue multiples, not P/E.",
  "The buyers must be price-inelastic. That decides how far prices can rise, and when.",
  "Supply barely doubles by 2030, so the old gluts may not return.",
];

export function CambrianThesis() {
  return (
    <section
      className="on-canvas flex flex-col gap-lg rounded-xl bg-canvas p-md text-on-canvas sm:p-lg"
      aria-labelledby="cambrian-thesis"
    >
      <header className="flex flex-col gap-xs">
        <p className="font-display text-label uppercase tracking-label text-verdigris-paper">
          The thesis · Cambrian Capital, September 2026
        </p>
        <h2 id="cambrian-thesis" className="font-display text-display-sm text-on-canvas">
          Own the bottleneck, not the model
        </h2>
        <ol className="mt-xs grid max-w-measure list-decimal gap-2xs pl-lg text-body-sm text-on-canvas-soft">
          {CHAIN.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ol>
      </header>

      <Figure
        title="Revenue multiples by segment"
        kind="computed"
      >
        <SegmentMultiples />
      </Figure>

      <div className="grid gap-md lg:grid-cols-2">
        <Figure
          title="How fast can supply scale?"
          kind="estimate"
          note="Central case, indexed to 2026. Cambrian cites TrendForce, Micron, Kioxia, SEMI, SUMCO and Murata. Annual growth: DRAM ~23%, NAND ~19%, MLCCs ~13%, wafers ~9%."
        >
          <SupplyGrowth />
        </Figure>
        <Figure title="Operating leverage, worked" kind="computed">
          <TorqueCalculator />
        </Figure>
      </div>

      <Figure
        title="Who cuts volume first when prices rise"
        kind="estimate"
        note="'Cuts at' is the price rise at which that buyer group starts buying less. Memory began with a price-sensitive base, which is part of why its prices surged only in Q4 2025. A wafer is ~$80 inside a $20k+ product, so even with ~10% AI exposure wafers can reprice."
      >
        <div className="grid gap-md lg:grid-cols-2">
          <BuyerTable title="Memory buyers, 2025" verdict="~55% price sensitive" rows={MEMORY_BUYERS} />
          <BuyerTable title="Wafer buyers, 2026" verdict="~5% price sensitive" rows={WAFER_BUYERS} />
        </div>
      </Figure>

      <div className="grid gap-md lg:grid-cols-2">
        <Figure title="Infrastructure wins in more worlds" kind="estimate">
          <FiveWorlds />
        </Figure>
        <Figure title="Where this desk is careful" kind="view">
          <ul className="flex list-disc flex-col gap-xs pl-md text-body-xs text-on-canvas-soft">
            <li>
              <span className="text-on-canvas">It is a bet on a fast AI timeline.</span> If demand
              slows, idle capacity is idle capacity. The numbers that score well here are the ones
              a cyclical bust is made of, which is why the balance sheet carries 15 points.
            </li>
            <li>
              <span className="text-on-canvas">Memory is a price-taker.</span> This desk's own
              principles exclude businesses whose price they do not set. Cambrian's answer is that
              inelastic buyers now set it. Memory rows are flagged, not resolved.
            </li>
            <li>
              <span className="text-on-canvas">Their named risk is memory compression.</span>{" "}
              Memory per token of context fell ~450× from GPT-3 to DeepSeek V4, while the DRAM price
              per bit rose 5–8×. Memory also went from under 10% of a GPU server's cost to ~25%,
              which pushes buyers to look for savings.
            </li>
            <li>
              <span className="text-on-canvas">Price sensitivity is not scored.</span> Cambrian
              estimates it by buyer group. A segment figure copied onto every company would rank
              nothing.
            </li>
          </ul>
        </Figure>
      </div>

      <p className="text-body-xs text-on-canvas-faint">
        Estimates copied from{" "}
        <a href={SOURCE} target="_blank" rel="noreferrer" className="text-cobalt-paper underline">
          Cambrian's published thesis
        </a>{" "}
        as of September 25, 2026. This desk did not compute them and cannot check them.
      </p>
    </section>
  );
}
