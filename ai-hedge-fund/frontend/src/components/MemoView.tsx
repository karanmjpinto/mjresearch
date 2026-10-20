import { useEffect, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AppNav } from "./AppNav";
import { humanizePersonaId } from "./PersonaOpinionCards";
import { api } from "@/lib/api";
import { formatValue } from "@/lib/format";
import { stagePath } from "@/lib/flow";
import { quadrantOf, timingSignals, timingVerdict, type Tone } from "@/lib/timing";
import { FootballField, MacroMini, PriceChart, SignalList, TONE_COLOR, ToneTag, type FieldRow } from "./MemoGraphics";

/**
 * The evaluation of one company, as a document someone can take away.
 *
 * Two lengths from the same data: a one-pager (verdict, stat block, value,
 * bull vs bear, risks) and a full memo that adds the committee, the claim
 * check, peers, the earnings record and every source. "Download" is the
 * browser's print-to-PDF: the sheet is ordinary DOM on the canvas ground, so
 * it prints exactly as it reads and needs no PDF library.
 *
 * It never runs the model. The prose comes from the newest saved run for the
 * name, so opening a memo costs nothing and says which run it is quoting. With
 * no run yet, the numbers still print and the prose sections say where to go.
 */

type Length = "one" | "full";

const pct = (v: number | null | undefined, signed = false) =>
  v == null || !Number.isFinite(v)
    ? "—"
    : `${signed && v > 0 ? "+" : ""}${v.toFixed(1)}%`;
const money = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? "—" : `$${formatValue(v)}`;
const mult = (v: unknown) =>
  typeof v === "number" && Number.isFinite(v) ? `${v.toFixed(1)}x` : "—";
const num = (v: unknown) => (typeof v === "number" ? v : null);

export function MemoView() {
  const { ticker: raw = "" } = useParams();
  const ticker = raw.toUpperCase();
  const [params, setParams] = useSearchParams();
  const length: Length = params.get("length") === "full" ? "full" : "one";
  const full = length === "full";

  const q = { enabled: Boolean(ticker), retry: false, staleTime: 5 * 60_000 };
  const fundamentals = useQuery({ ...q, queryKey: ["fundamentals", ticker], queryFn: () => api.getFundamentals(ticker) });
  const runs = useQuery({ ...q, queryKey: ["runs", ticker], queryFn: () => api.getRuns(ticker, 20) });
  const comps = useQuery({ ...q, queryKey: ["comps-range", ticker], queryFn: () => api.getCompsRange(ticker) });
  const intrinsic = useQuery({ ...q, queryKey: ["memo-intrinsic", ticker], queryFn: () => api.getIntrinsic(ticker) });
  const analyst = useQuery({ ...q, queryKey: ["analyst", ticker], queryFn: () => api.getAnalyst(ticker) });
  const earnings = useQuery({ ...q, queryKey: ["earnings", ticker], queryFn: () => api.getEarnings(ticker) });
  const peers = useQuery({ ...q, enabled: q.enabled && full, queryKey: ["peers", ticker], queryFn: () => api.getPeers(ticker) });
  const prices = useQuery({ ...q, queryKey: ["memo-price", ticker], queryFn: () => api.getPrice(ticker, 420) });
  const technicals = useQuery({ ...q, queryKey: ["technicals", ticker], queryFn: () => api.getTechnicals(ticker) });
  const macroPoint = useQuery({ ...q, queryKey: ["macro-point", ticker], queryFn: () => api.getMacroPoint(ticker) });
  const macroMap = useQuery({ ...q, queryKey: ["macro-map"], queryFn: api.getMacroMap, staleTime: Infinity });
  const regimes = useQuery({ ...q, queryKey: ["memo-regimes", ticker], queryFn: () => api.getRegimes(ticker) });
  const decisions = useQuery({ ...q, enabled: q.enabled && full, queryKey: ["decisions", ticker], queryFn: () => api.getDecisions(ticker, 10) });

  // Plan runs carry a different output; only a run with a thesis can be quoted.
  const latest = runs.data?.runs.find(
    (r) => (r.output as { investment_thesis?: string } | undefined)?.investment_thesis,
  );
  const run = useQuery({
    ...q,
    enabled: Boolean(latest),
    queryKey: ["run", latest?.run_uid],
    queryFn: () => api.getRun(latest!.run_uid),
  });

  const f = fundamentals.data ?? {};
  const name = (f.name as string | undefined) ?? ticker;
  const ai = run.data?.output;
  // Local date: the UTC one is a day off for anyone east of Greenwich after midnight.
  const today = new Date().toLocaleDateString("en-CA");

  // The PDF takes its default filename from the title.
  useEffect(() => {
    const prev = document.title;
    document.title = `${ticker} ${full ? "investment memo" : "one-pager"} ${today}`;
    return () => {
      document.title = prev;
    };
  }, [ticker, full, today]);

  const loading = [fundamentals, runs, run, comps, analyst, prices, technicals, macroPoint, macroMap, regimes].some((x) => x.isLoading);

  const price = num(comps.data?.price) ?? num(analyst.data?.current_price);
  const mcap = num(f.market_cap);
  const revenue = num(f.revenue);
  const fcf = num(f.free_cash_flow);
  const ni = num(f.net_income);
  const cs = comps.data?.summary;
  const iv = intrinsic.data;
  const ivValue = iv?.available ? iv.base_case.value_per_share : null;
  const tech = technicals.data ?? {};
  const point = macroPoint.data?.point ?? null;
  // The macro map scores twelve-month windows, so "now" is the last four quarters of news.
  const ctx = macroMap.data?.context;
  const sum4 = (xs: number[] | undefined) => xs?.slice(-4).reduce((a, b) => a + b, 0);
  const nowQuadrant = ctx ? quadrantOf(sum4(ctx.inflation.news)!, sum4(ctx.growth.news)!) : null;
  const regimeNow = regimes.data?.current;
  const signals = timingSignals({
    price,
    sma50: num(tech.sma_50),
    sma200: num(tech.sma_200),
    rsi: num(tech.rsi_14),
    low52: num(f["52w_low"]),
    high52: num(f["52w_high"]),
    compsMid: cs?.available ? cs.mid : null,
    streetTarget: analyst.data?.target_mean ?? null,
    stockQuadrant: point?.quadrant ?? null,
    nowQuadrant,
    regime: regimeNow && (regimes.data?.centroids.length ?? 0) > 1 ? { name: regimeNow.name, days: regimeNow.run_days } : null,
  });
  const verdict = timingVerdict(signals);
  const priceRows = (prices.data?.data ?? [])
    .map((r) => ({ date: String(r.date), close: Number(r.close) }))
    .filter((r) => Number.isFinite(r.close));
  const a = analyst.data;
  const field: FieldRow[] = [
    ...(comps.data?.bands ?? [])
      .filter((b) => b.applicable)
      .map((b) => ({ label: `Peer ${b.label}`, low: b.low, high: b.high, mid: b.mid, color: "var(--cobalt-paper)" })),
    ...(iv?.available
      ? [{ label: "Intrinsic (DCF)", low: iv.distribution.percentiles.p10 ?? ivValue!, high: iv.distribution.percentiles.p90 ?? ivValue!, mid: ivValue!, color: "var(--verdigris-paper)" }]
      : []),
    ...(a?.target_low != null && a.target_high != null
      ? [{ label: "Street targets", low: a.target_low, high: a.target_high, mid: a.target_mean ?? undefined, color: "var(--cadmium-paper)" }]
      : []),
    ...(num(f["52w_low"]) != null && num(f["52w_high"]) != null
      ? [{ label: "52-week range", low: num(f["52w_low"])!, high: num(f["52w_high"])!, color: "var(--aluminium)" }]
      : []),
  ];

  return (
    <div className="min-h-screen bg-ink print:bg-paper">
      <div className="print:hidden">
        <AppNav active="evaluate" />
      </div>

      <main className="mx-auto max-w-4xl px-md py-lg sm:px-lg print:max-w-none print:p-0">
        <div className="mb-md flex flex-wrap items-center justify-between gap-sm print:hidden">
          <div role="group" aria-label="Memo length" className="flex border border-ink-line">
            {(
              [
                ["one", "One-pager"],
                ["full", "Full memo"],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                type="button"
                aria-pressed={length === k}
                onClick={() => setParams({ length: k }, { replace: true })}
                className={`px-md py-xs font-display text-label uppercase tracking-label transition-colors ${
                  length === k
                    ? "bg-cobalt text-on-accent-light"
                    : "text-on-ink-soft hover:text-bone"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => window.print()}
            disabled={loading}
            className="border border-cobalt bg-cobalt px-md py-xs font-display text-label uppercase tracking-label text-on-accent-light transition-opacity hover:opacity-90 disabled:cursor-wait disabled:opacity-50"
          >
            {loading ? "Gathering…" : "Download PDF"}
          </button>
        </div>

        <article className={`on-canvas ${full ? "" : "memo-one-page"} memo-sheet bg-paper px-lg py-xl text-on-canvas shadow-elev-1 sm:px-xl print:shadow-none`}>
          {/* The four thrown colours, as a band: the brand, at the weight of a rule. */}
          <div aria-hidden="true" className="memo-band -mx-lg -mt-xl mb-lg flex h-2 sm:-mx-xl">
            {["--oxide-paper", "--cadmium-paper", "--cobalt-paper", "--verdigris-paper"].map((c) => (
              <span key={c} className="flex-1" style={{ background: `var(${c})` }} />
            ))}
          </div>
          <header className="border-b-2 border-on-canvas pb-sm">
            <div className="flex items-baseline justify-between gap-sm">
              <p className="font-display text-label uppercase tracking-marker text-on-canvas-faint">
                {full ? "Investment memo" : "One-pager"} · {today}
              </p>
              <p className="font-display text-label uppercase tracking-marker text-on-canvas">
                MJ <span className="text-cobalt-paper">Research</span>
              </p>
            </div>
            <h1 className="mt-xs font-display text-display-sm text-on-canvas">
              {name} <span className="text-cadmium-paper">{ticker}</span>
            </h1>
            <p className="mt-2xs text-body-xs text-on-canvas-soft">
              {[f.exchange, f.sector, f.industry].filter(Boolean).join(" · ") || "—"}
            </p>
          </header>

          <dl className="grid grid-cols-2 border-b border-canvas-deep sm:grid-cols-4">
            <Verdict label="Stance" value={ai?.stance ?? "—"} tone={STANCE_TONE[ai?.stance ?? ""]} />
            <Verdict label="Conviction" value={ai?.conviction_score != null ? `${ai.conviction_score} / 100` : "—"} />
            <Verdict label="Horizon" value={ai?.time_horizon?.replace(/_/g, " ") || "—"} />
            <Verdict label="Data confidence" value={ai?.confidence_in_data != null ? `${ai.confidence_in_data} / 5` : "—"} />
          </dl>

          <Section title="Is now the time?" color="var(--cadmium-paper)">
            {verdict && (
              <p className="mb-xs flex flex-wrap items-center gap-xs font-display text-mark" style={{ color: TONE_COLOR[verdict.tone] }}>
                <ToneTag tone={verdict.tone} /> {verdict.text}
              </p>
            )}
            {signals.length > 0 ? <SignalList signals={signals} /> : <Missing>{loading ? "Reading the market…" : "No timing data for this name."}</Missing>}
            <div className="mt-sm grid items-start gap-md sm:grid-cols-[1fr_200px] print:grid-cols-[1fr_200px]">
              {priceRows.length > 0 ? <PriceChart rows={priceRows} height={full ? 180 : 130} /> : <span />}
              {point && <MacroMini point={point} now={nowQuadrant} />}
            </div>
            <p className={`mt-2xs text-body-xs text-on-canvas-faint ${full ? "" : "print:hidden"}`}>
              Computed from the readings above, not the model's verdict. Thresholds: RSI 30/70, 20% and 85% of the 52-week range, 10% from peer value, 15% to the street target.
            </p>
          </Section>

          <Section title="The trade">
            {ai?.investment_thesis ? (
              <Prose>{ai.investment_thesis}</Prose>
            ) : (
              <Missing>
                {runs.isLoading || run.isLoading
                  ? "Reading the latest run…"
                  : <>No model view of {ticker} has been run yet. Run the committee in{" "}
                    <Link className="text-cobalt-paper underline" to={stagePath("analysis", ticker)}>Analysis</Link>{" "}
                    and the thesis, cases and risks will fill in here.</>}
              </Missing>
            )}
          </Section>

          <Section title="Stat block">
            <dl className={`grid grid-cols-1 gap-x-lg sm:grid-cols-2 ${full ? "print:grid-cols-2" : "lg:grid-cols-4 print:grid-cols-4 print:gap-x-md"}`}>
              <Stat k="Price" v={money(price)} />
              <Stat k="Market cap" v={money(mcap)} />
              <Stat extra={!full} k="Revenue (LTM)" v={money(revenue)} />
              <Stat extra={!full} k="EBITDA" v={money(num(f.ebitda))} />
              <Stat k="Net margin" v={revenue && ni != null ? pct((ni / revenue) * 100) : "—"} />
              <Stat extra={!full} k="Free cash flow" v={money(fcf)} />
              <Stat k="FCF yield" v={mcap && fcf != null ? pct((fcf / mcap) * 100) : "—"} />
              <Stat extra={!full} k="Total debt" v={money(num(f.total_debt))} />
              <Stat k="P/E · forward" v={`${mult(f.pe_ratio)} · ${mult(f.forward_pe)}`} />
              <Stat extra={!full} k="PEG · P/B" v={`${formatValue(num(f.peg_ratio))} · ${mult(f.price_to_book)}`} />
              <Stat k="52-week range" v={`${money(num(f["52w_low"]))} – ${money(num(f["52w_high"]))}`} />
              <Stat extra={!full} k="Beta · dividend yield" v={`${formatValue(num(f.beta))} · ${pct(num(f.dividend_yield))}`} />
              <Stat k="Next print" v={earnings.data?.next_earnings_date ?? "—"} />
              <Stat extra={!full} k="Currency" v={(f.currency as string | undefined) ?? "—"} />
            </dl>
          </Section>

          <Section title="What it is worth" color="var(--verdigris-paper)">
            <FootballField rows={field} price={price} />
            <table className={`mt-xs w-full text-body-xs ${full ? "" : "hidden"}`}>
              <thead>
                <tr className="border-b border-canvas-deep text-left font-display text-label uppercase tracking-label text-on-canvas-faint">
                  <th className="py-2xs font-normal">Method</th>
                  <th className="py-2xs text-right font-normal">Value / share</th>
                  <th className="py-2xs text-right font-normal">vs price</th>
                  <th className="hidden py-2xs pl-md font-normal sm:table-cell print:table-cell">Basis</th>
                </tr>
              </thead>
              <tbody className="tabular">
                <ValueRow
                  method="Peer multiples (mid)"
                  value={cs?.available ? cs.mid : null}
                  price={price}
                  basis={cs?.available
                    ? `range ${money(cs.low)}–${money(cs.high)}, ${cs.methods} methods, ${comps.data?.vetted ? "curated" : "unvetted"} peers`
                    : cs?.reason ?? "—"}
                />
                <ValueRow
                  method="Intrinsic (DCF base)"
                  value={ivValue}
                  price={price}
                  basis={iv?.available
                    ? `P(value > price) ${pct((iv.distribution.probability_value_above_price ?? NaN) * 100)}`
                    : iv
                      ? `not computed: ${iv.missing.join(", ").replace(/_/g, " ") || iv.reason}`
                      : "—"}
                />
                <ValueRow
                  method="Street target (mean)"
                  value={analyst.data?.target_mean ?? null}
                  price={price}
                  basis={analyst.data?.num_analysts
                    ? `${analyst.data.num_analysts} analysts, ${analyst.data.recommendation?.replace(/_/g, " ") ?? "no rating"}`
                    : "—"}
                />
              </tbody>
            </table>
          </Section>

          <div className="grid gap-x-lg sm:grid-cols-2 print:grid-cols-2">
            <Section title="Bull case" color="var(--verdigris-paper)">
              {ai?.bull_case ? <Prose>{ai.bull_case}</Prose> : <Missing>—</Missing>}
            </Section>
            <Section title="Bear case" color="var(--oxide-paper)">
              {ai?.bear_case ? <Prose>{ai.bear_case}</Prose> : <Missing>—</Missing>}
              {!full && (ai?.key_risks?.length ?? 0) > 0 && (
                <ol className="mt-xs list-decimal space-y-2xs pl-md text-body-xs text-on-canvas">
                  {ai!.key_risks!.slice(0, 3).map((r) => <li key={r}>{r}</li>)}
                </ol>
              )}
            </Section>
          </div>

          {full && (ai?.key_risks?.length ?? 0) > 0 && (
            <Section title="Key risks" color="var(--oxide-paper)">
              <ol className="list-decimal space-y-2xs pl-md text-body-xs text-on-canvas">
                {ai!.key_risks!.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ol>
            </Section>
          )}

          {full && <FullSections ticker={ticker} run={run.data} comps={comps.data} peers={peers.data} earnings={earnings.data} decisions={decisions.data} intrinsicNotes={iv && !iv.available ? iv.notes : undefined} />}

          <footer className={`${full ? "" : "memo-foot"} mt-lg border-t border-canvas-deep pt-sm text-body-xs text-on-canvas-faint`}>
            {run.data
              ? `Prose from the ${run.data.mode} run of ${run.data.created_at.slice(0, 10)} (${run.data.model ?? "model unknown"}). `
              : "No model run quoted. "}
            Numbers from {(f.source as string | undefined) ?? "the data layer"}, pulled {today}. Written prose
            is a model's judgment and can misstate a figure; where it disagrees with the stat block, the stat block
            is the authority. Not investment advice.
          </footer>
          {/* Fixed in print, so it lands bottom-right on every page. */}
          <p className="memo-brand mt-sm text-right font-display text-label uppercase tracking-marker text-on-canvas">
            MJ <span className="text-cobalt-paper">Research</span>
          </p>
        </article>
      </main>
    </div>
  );
}

type RunData = Awaited<ReturnType<typeof api.getRun>>;

function FullSections({
  ticker,
  run,
  comps,
  peers,
  earnings,
  decisions,
  intrinsicNotes,
}: {
  ticker: string;
  run: RunData | undefined;
  comps: Awaited<ReturnType<typeof api.getCompsRange>> | undefined;
  peers: Awaited<ReturnType<typeof api.getPeers>> | undefined;
  earnings: Awaited<ReturnType<typeof api.getEarnings>> | undefined;
  decisions: Awaited<ReturnType<typeof api.getDecisions>> | undefined;
  intrinsicNotes?: string[];
}) {
  const v = run?.verification;
  // Rebuttal rounds are stored beside round one; the later entry is the view the PM reconciled.
  const committee = [
    ...new Map((run?.committee_detail ?? []).filter((c) => c.analysis).map((c) => [c.persona_id, c])).values(),
  ];
  const peerRows = peers ? Object.entries(peers.metrics) : [];
  const reported = (earnings?.earnings_dates ?? []).filter((e) => e.reported_eps != null).slice(0, 6);

  return (
    <>
      <Section title="Trust check" breakBefore>
        {v && v.checked > 0 ? (
          <>
            <Prose>
              {`Every number the prose states was checked against the data the run saw: ${v.checked} checked, ${v.verified} verified, ${v.mismatched} mismatched, ${v.unverifiable} unverifiable.`}
            </Prose>
            <Table
              head={["Claim", "Stated", "Data", "Verdict"]}
              rows={v.claims.map((c) => [c.metric.replace(/_/g, " "), formatValue(c.stated), formatValue(c.actual ?? null), c.verdict])}
              tone={(row) => (row[3] === "mismatched" ? "text-oxide-paper" : undefined)}
            />
          </>
        ) : (
          <Missing>No stated numbers were checked for this run.</Missing>
        )}
      </Section>

      {committee.length > 0 && (
        <Section title="The committee">
          <Table
            head={["Investor", "Stance", "Conviction", "Their thesis"]}
            rows={committee.map((c) => [
              humanizePersonaId(c.persona_id),
              c.analysis!.stance,
              String(c.analysis!.conviction_score),
              c.analysis!.investment_thesis || "Returned no reasoning.",
            ])}
            wide={3}
          />
        </Section>
      )}

      {comps && comps.bands.length > 0 && (
        <Section title="Peer multiples">
          <Table
            head={["Multiple", `${ticker}`, "Peer mid", "Implied low – high"]}
            rows={comps.bands.map((b) => [
              b.label + (b.applicable ? "" : " (excluded)"),
              mult(b.subject_multiple),
              mult(b.peer_multiple.mid),
              `${money(b.low)} – ${money(b.high)}`,
            ])}
          />
          <p className="mt-2xs text-body-xs text-on-canvas-faint">
            Peers: {comps.peers.join(", ")} ({comps.basis === "curated" ? "hand-picked" : "by industry code"}).
          </p>
        </Section>
      )}

      {peerRows.length > 0 && (
        <Section title="Against peers">
          <Table
            head={["Ticker", "P/E", "Fwd P/E", "Net margin", "ROE", "Rev growth", "Mkt cap"]}
            rows={peerRows.map(([t, m]) => [
              t,
              mult(m.pe_ratio),
              mult(m.forward_pe),
              pct(m.profit_margin != null ? m.profit_margin * 100 : null),
              pct(m.return_on_equity != null ? m.return_on_equity * 100 : null),
              pct(m.revenue_growth != null ? m.revenue_growth * 100 : null),
              money(m.market_cap),
            ])}
            tone={(row) => (row[0] === ticker ? "font-semibold" : undefined)}
          />
        </Section>
      )}

      {reported.length > 0 && (
        <Section title="Earnings record">
          <Table
            head={["Date", "Estimate", "Reported", "Surprise"]}
            rows={reported.map((e) => [e.date, formatValue(e.eps_estimate), formatValue(e.reported_eps), pct(e.surprise_pct, true)])}
          />
        </Section>
      )}

      <Section title="Decisions on file">
        {decisions && decisions.decisions.length > 0 ? (
          <Table
            head={["Date", "Action", "Rationale"]}
            rows={decisions.decisions.map((d) => [d.created_at?.slice(0, 10) ?? "—", d.action, d.rationale ?? "—"])}
            wide={2}
          />
        ) : (
          <Missing>No decision recorded for {ticker} yet.</Missing>
        )}
      </Section>

      {intrinsicNotes && intrinsicNotes.length > 0 && (
        <Section title="Caveats on the valuation">
          <ul className="list-disc space-y-2xs pl-md text-body-xs text-on-canvas-soft">
            {intrinsicNotes.map((n) => <li key={n}>{n}</li>)}
          </ul>
        </Section>
      )}
    </>
  );
}

function Section({ title, children, breakBefore, color = "var(--cobalt-paper)" }: { title: string; children: ReactNode; breakBefore?: boolean; color?: string }) {
  return (
    <section className={`mt-lg break-inside-avoid-page print:mt-md ${breakBefore ? "print:break-before-page" : ""}`}>
      <h2 className="mb-xs flex items-center gap-xs border-b border-canvas-deep pb-2xs font-display text-label uppercase tracking-marker text-on-canvas">
        <span aria-hidden="true" className="inline-block h-2.5 w-2.5" style={{ background: color }} />
        {title}
      </h2>
      {children}
    </section>
  );
}

function Prose({ children }: { children: ReactNode }) {
  return <p className="max-w-[80ch] whitespace-pre-line text-body-sm text-on-canvas">{children}</p>;
}

function Missing({ children }: { children: ReactNode }) {
  return <p className="text-body-xs text-on-canvas-faint">{children}</p>;
}

const STANCE_TONE: Record<string, Tone> = { BUY: "go", HOLD: "wait", WATCH: "wait", SELL: "stop" };

function Verdict({ label, value, tone }: { label: string; value: string; tone?: Tone }) {
  return (
    <div className="py-sm pr-sm">
      <dt className="font-display text-label uppercase tracking-label text-on-canvas-faint">{label}</dt>
      <dd className="mt-2xs font-display text-mark capitalize text-on-canvas">
        {tone ? (
          <span className="px-xs text-on-accent-light" style={{ background: TONE_COLOR[tone] }}>{value}</span>
        ) : (
          value
        )}
      </dd>
    </div>
  );
}

function Stat({ k, v, extra }: { k: string; v: string; extra?: boolean }) {
  return (
    <div className={`${extra ? "hidden" : "flex"} items-baseline justify-between gap-sm border-b border-canvas-deep py-2xs text-body-xs`}>
      <dt className="text-on-canvas-soft">{k}</dt>
      <dd className="tabular text-right text-on-canvas">{v}</dd>
    </div>
  );
}

function ValueRow({ method, value, price, basis }: { method: string; value: number | null | undefined; price: number | null; basis: string }) {
  const gap = value != null && price ? ((value - price) / price) * 100 : null;
  return (
    <tr className="border-b border-canvas-deep align-top">
      <td className="py-2xs text-on-canvas-soft">{method}</td>
      <td className="py-2xs text-right text-on-canvas">{money(value)}</td>
      <td className={`py-2xs text-right ${gap == null ? "" : gap >= 0 ? "text-verdigris-paper" : "text-oxide-paper"}`}>{pct(gap, true)}</td>
      <td className="hidden py-2xs pl-md text-on-canvas-faint sm:table-cell print:table-cell">{basis}</td>
    </tr>
  );
}

function Table({
  head,
  rows,
  tone,
  wide,
}: {
  head: string[];
  rows: string[][];
  tone?: (row: string[]) => string | undefined;
  /** Index of the free-text column, which wraps instead of the numbers. */
  wide?: number;
}) {
  return (
    <div className="overflow-x-auto print:overflow-visible">
      <table className="w-full text-body-xs">
        <thead>
          <tr className="border-b border-canvas-deep text-left font-display text-label uppercase tracking-label text-on-canvas-faint">
            {head.map((h, i) => (
              <th key={h} className={`py-2xs pr-sm font-normal ${i > 0 && i !== wide ? "text-right" : ""}`}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular">
          {rows.map((r, ri) => (
            <tr key={ri} className={`border-b border-canvas-deep align-top ${tone?.(r) ?? ""}`}>
              {r.map((c, i) => (
                <td
                  key={i}
                  className={`py-2xs pr-sm ${i > 0 && i !== wide ? "whitespace-nowrap text-right" : ""} ${i === wide ? "min-w-[24ch]" : ""}`}
                >
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
