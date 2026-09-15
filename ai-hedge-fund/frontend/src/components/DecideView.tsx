import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { AppNav } from "@/components/AppNav";
import { ConcentrationPanel } from "@/components/ConcentrationPanel";
import { api, type DecisionRow, type SizingAssessment } from "@/lib/api";
import { useTicker } from "@/lib/ticker-context";

/**
 * Decide — the step between having a view and having a position.
 *
 * A conviction score says whether a name is good. It does not say whether you
 * should own it, because that depends on what you already hold: a strong idea
 * that moves with the rest of the book adds risk without adding much, and a
 * merely decent one that moves differently can still earn its place. So the
 * sizing here is expressed against the existing portfolio rather than in
 * isolation, and the decision is recorded with that context attached — a call
 * reviewed a year from now has to be judged against the book as it was.
 */

const ACTIONS = ["buy", "watch", "hold", "sell", "pass"] as const;

const ACTION_TONE: Record<string, string> = {
  buy: "bg-verdigris text-on-accent",
  sell: "bg-oxide text-on-accent-light",
  hold: "bg-cadmium text-on-accent",
  watch: "bg-cobalt text-on-accent-light",
  pass: "bg-ink-line text-on-ink",
};

const n = (v: number | null | undefined, dp = 2, suffix = "") =>
  v === null || v === undefined || !Number.isFinite(v)
    ? "—"
    : `${v.toFixed(dp)}${suffix}`;

function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: string;
}) {
  return (
    <div className="bg-ink-raised px-lg py-md">
      <div
        className={`font-display text-[20px] tabular ${tone ?? "text-bone"}`}
      >
        {value}
      </div>
      <div className="mt-2xs font-display text-label uppercase tracking-[0.13em] text-on-ink-faint">
        {label}
      </div>
      {sub && <div className="mt-1 text-label text-on-ink-faint">{sub}</div>}
    </div>
  );
}

function SizingPanel({ a }: { a: SizingAssessment }) {
  const volTone =
    a.diversifying === true
      ? "text-verdigris"
      : a.diversifying === false
        ? "text-oxide"
        : "text-bone";
  return (
    <>
      <div className="grid gap-px bg-ink-line sm:grid-cols-4">
        <Stat
          label="of the book"
          value={n(a.proposed_weight_pct, 1, "%")}
          sub={
            a.rank_after
              ? `would rank #${a.rank_after} of ${a.holdings_after}`
              : undefined
          }
        />
        <Stat
          label="correlation to book"
          value={n(a.correlation_to_book, 2)}
          sub={
            a.overlap_observations
              ? `${a.overlap_observations} overlapping days`
              : "not enough overlap"
          }
          tone={
            a.correlation_to_book !== null && a.correlation_to_book >= 0.75
              ? "text-oxide"
              : a.correlation_to_book !== null && a.correlation_to_book < 0.3
                ? "text-verdigris"
                : "text-bone"
          }
        />
        <Stat
          label="portfolio volatility"
          value={`${n(a.portfolio_volatility_before_pct, 1)}% → ${n(a.portfolio_volatility_after_pct, 1)}%`}
          sub={
            a.volatility_change_pct === null
              ? undefined
              : `${a.volatility_change_pct > 0 ? "+" : ""}${a.volatility_change_pct.toFixed(2)} points`
          }
          tone={volTone}
        />
        <Stat
          label="cash after"
          value={n(a.cash_after, 0)}
          sub={`${a.currency} · own vol ${n(a.candidate_volatility_pct, 0, "%")}`}
          tone={a.funded_by_cash ? "text-bone" : "text-oxide"}
        />
      </div>

      {(a.concentration_top3_before_pct !== null || a.existing_weight_pct) && (
        <p className="mt-sm text-[13px] leading-relaxed text-on-ink-soft">
          Top three holdings{" "}
          <span className="font-display text-bone">
            {n(a.concentration_top3_before_pct, 0, "%")} →{" "}
            {n(a.concentration_top3_after_pct, 0, "%")}
          </span>
          {a.existing_weight_pct ? (
            <>
              . You already hold{" "}
              <span className="font-display text-bone">
                {n(a.existing_weight_pct, 1, "%")}
              </span>{" "}
              of this name.
            </>
          ) : (
            ". This would be a new position."
          )}
        </p>
      )}

      {a.flags.map((f) => (
        <p
          key={f}
          className="mt-sm bg-oxide/15 px-md py-sm text-[13px] leading-relaxed text-oxide"
        >
          {f}
        </p>
      ))}
      {a.notes.length > 0 && (
        <ul className="mt-sm space-y-1">
          {a.notes.map((note) => (
            <li
              key={note}
              className="text-[12px] leading-relaxed text-on-ink-faint"
            >
              {note}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function DecisionCard({ d }: { d: DecisionRow }) {
  const o = d.outcome;
  const favour = o?.scored ? (o.in_your_favour_pct ?? 0) : null;
  return (
    <article className="border-t border-ink-line px-lg py-md first:border-t-0">
      <div className="flex flex-wrap items-baseline gap-sm">
        <span
          className={`px-2 py-0.5 font-display text-label uppercase tracking-[0.12em] ${ACTION_TONE[d.action] ?? "bg-ink-line text-on-ink"}`}
        >
          {d.action}
        </span>
        <span className="font-display text-[14px] text-bone">{d.ticker}</span>
        {d.conviction !== null && (
          <span className="font-display text-[12px] tabular text-on-ink-faint">
            conviction {d.conviction}
          </span>
        )}
        {d.proposed_weight_pct !== null && (
          <span className="font-display text-[12px] tabular text-cadmium">
            {d.proposed_weight_pct.toFixed(1)}% of book
          </span>
        )}
        <span className="ml-auto font-display text-label text-on-ink-faint">
          {d.created_at?.slice(0, 10)}
        </span>
      </div>

      {d.rationale && (
        <p className="mt-2xs max-w-[80ch] text-[13px] leading-relaxed text-on-ink-soft">
          {d.rationale}
        </p>
      )}

      {favour !== null && (
        <p className="mt-sm font-display text-[12px] tabular">
          <span className={favour >= 0 ? "text-verdigris" : "text-oxide"}>
            {favour >= 0 ? "+" : ""}
            {favour.toFixed(1)}% in your favour
          </span>
          <span className="ml-sm text-on-ink-faint">
            since {n(d.price_at_decision, 2)} → {n(o?.current_price, 2)}
          </span>
        </p>
      )}
    </article>
  );
}

/** Research context handed over from a plan run, if the user came that way. */
type CarriedResearch = {
  conviction?: number | null;
  stance?: string | null;
  thesis?: string | null;
  run_uid?: string | null;
};

export function DecideView() {
  const { ticker: routeTicker } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const { ticker: activeTicker, setTicker: setActiveTicker } = useTicker();

  const carried = (location.state ?? {}) as CarriedResearch;
  const [ticker, setTicker] = useState(
    (routeTicker ?? activeTicker ?? "").toUpperCase(),
  );
  const [amount, setAmount] = useState<string>("");
  const [action, setAction] = useState<string>("buy");
  const [rationale, setRationale] = useState("");
  const [assessment, setAssessment] = useState<SizingAssessment | null>(null);

  const history = useQuery({
    queryKey: ["decisions", ticker],
    queryFn: () => api.getDecisions(ticker || undefined, 50),
  });

  useEffect(() => {
    if (ticker && ticker !== activeTicker) setActiveTicker(ticker);
  }, [ticker, activeTicker, setActiveTicker]);

  const size = useMutation({
    mutationFn: () =>
      api.sizePosition(
        amount.trim()
          ? { ticker, amount: Number(amount) }
          : { ticker, weight_pct: 5 },
      ),
    onSuccess: (r) => setAssessment(r.assessment),
  });

  const decide = useMutation({
    mutationFn: () =>
      api.recordDecision({
        ticker,
        action,
        rationale: rationale.trim(),
        amount: amount.trim() ? Number(amount) : undefined,
        conviction: carried.conviction ?? undefined,
        stance: carried.stance ?? undefined,
        research_run_uid: carried.run_uid ?? undefined,
      }),
    onSuccess: () => {
      setRationale("");
      qc.invalidateQueries({ queryKey: ["decisions"] });
    },
  });

  return (
    <div className="min-h-screen bg-ink">
      <AppNav active="decide" />

      <main className="mx-auto max-w-5xl px-lg py-xl">
        <header className="mb-lg">
          <h1 className="font-display text-display-sm tracking-tight text-bone">
            Decide
          </h1>
          <p className="mt-sm max-w-[72ch] text-[15px] leading-relaxed text-on-ink-soft">
            A conviction score tells you whether a name is good. Whether you
            should own it depends on what you already hold — so this sizes the
            position against your book, and records the call with that context
            attached.
          </p>
        </header>

        {ticker && (
          <div className="mb-lg border-t border-ink-line pt-lg">
            <ConcentrationPanel ticker={ticker.toUpperCase()} />
          </div>
        )}

        {carried.run_uid && (
          <div className="mb-lg border border-cobalt/40 bg-cobalt/10 px-lg py-md">
            <p className="font-display text-label uppercase tracking-[0.14em] text-cobalt">
              Carried from research
            </p>
            <p className="mt-2xs text-[13px] leading-relaxed text-on-ink-soft">
              {carried.stance ?? "—"} at conviction{" "}
              <span className="font-display tabular text-bone">
                {carried.conviction ?? "—"}
              </span>
              . This decision will be filed against run{" "}
              <span className="font-display text-on-ink-faint">
                {carried.run_uid.slice(0, 8)}
              </span>
              , so the reasoning stays attached to the call.
            </p>
          </div>
        )}

        <section className="border border-ink-line bg-ink-raised p-lg">
          <div className="grid gap-md sm:grid-cols-[150px_180px_auto] sm:items-end">
            <label className="block">
              <span className="mb-1 block font-display text-label uppercase tracking-[0.14em] text-on-ink-faint">
                Ticker
              </span>
              <input
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                placeholder="NVDA"
                className="w-full border border-ink-line bg-ink px-3 py-2 font-display text-[13px] text-bone outline-none focus:border-cobalt"
              />
            </label>
            <label className="block">
              <span className="mb-1 block font-display text-label uppercase tracking-[0.14em] text-on-ink-faint">
                Amount
              </span>
              <input
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="25000"
                inputMode="decimal"
                className="w-full border border-ink-line bg-ink px-3 py-2 font-display text-[13px] tabular text-bone outline-none focus:border-cobalt"
              />
            </label>
            <div className="flex gap-sm">
              <button
                type="button"
                onClick={() => size.mutate()}
                disabled={!ticker.trim() || size.isPending}
                className="bg-cobalt px-5 py-2.5 font-display text-label uppercase tracking-[0.14em] text-on-accent-light transition-colors hover:bg-cadmium hover:text-on-accent disabled:bg-ink-line disabled:text-on-ink-faint"
              >
                {size.isPending ? "Sizing…" : "Size against book"}
              </button>
              {ticker.trim() && (
                <button
                  type="button"
                  onClick={() => navigate(`/plan/${ticker}`)}
                  className="border border-ink-line px-4 py-2.5 font-display text-label uppercase tracking-[0.14em] text-on-ink transition-colors hover:border-bone hover:text-bone"
                >
                  Research first
                </button>
              )}
            </div>
          </div>
          {size.isError && (
            <p className="mt-sm text-[12px] text-oxide">
              {(size.error as Error).message}
            </p>
          )}
        </section>

        {assessment && (
          <section className="mt-lg">
            <h2 className="mb-sm font-display text-label uppercase tracking-[0.18em] text-on-ink-faint">
              Against your book
            </h2>
            <SizingPanel a={assessment} />

            <div className="mt-lg border border-ink-line bg-ink-raised p-lg">
              <h3 className="font-display text-label uppercase tracking-[0.18em] text-on-ink-faint">
                Record the call
              </h3>
              <div className="mt-sm flex flex-wrap gap-2xs">
                {ACTIONS.map((a) => (
                  <button
                    key={a}
                    type="button"
                    onClick={() => setAction(a)}
                    className={`px-4 py-2 font-display text-label uppercase tracking-[0.12em] transition-colors ${
                      action === a
                        ? ACTION_TONE[a]
                        : "bg-ink text-on-ink-faint hover:text-on-ink"
                    }`}
                  >
                    {a}
                  </button>
                ))}
              </div>
              <textarea
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                rows={3}
                aria-label="Decision rationale"
                placeholder="Why this, why now, and what would change your mind."
                className="mt-sm w-full resize-y border border-ink-line bg-ink px-3 py-2 text-[14px] leading-relaxed text-bone outline-none placeholder:text-on-ink-faint focus:border-cobalt"
              />
              <div className="mt-sm flex flex-wrap items-center gap-md">
                <button
                  type="button"
                  onClick={() => decide.mutate()}
                  disabled={!rationale.trim() || decide.isPending}
                  className="bg-verdigris px-5 py-2.5 font-display text-label uppercase tracking-[0.14em] text-on-accent transition-colors hover:bg-cadmium disabled:bg-ink-line disabled:text-on-ink-faint"
                >
                  {decide.isPending ? "Recording…" : "Record decision"}
                </button>
                <span className="text-[12px] text-on-ink-faint">
                  Saved with your current weights and correlation, so it can be
                  reviewed fairly later.
                </span>
              </div>
              {decide.isError && (
                <p className="mt-sm text-[12px] text-oxide">
                  {(decide.error as Error).message}
                </p>
              )}
            </div>
          </section>
        )}

        <section className="mt-xl border border-ink-line bg-ink-raised">
          <div className="flex items-baseline justify-between border-b border-ink-line px-lg py-sm">
            <h2 className="font-display text-label uppercase tracking-[0.18em] text-on-ink-faint">
              Decision log
            </h2>
            {ticker && (
              <span className="font-display text-label text-on-ink-faint">
                {ticker}
              </span>
            )}
          </div>
          {(history.data?.decisions ?? []).length === 0 ? (
            <p className="px-lg py-xl text-[13px] leading-relaxed text-on-ink-faint">
              No decisions recorded yet. Once you record one, it comes back here
              with the move since — so the question at review is whether the
              reasoning held, not just whether the price went up.
            </p>
          ) : (
            history.data?.decisions.map((d) => (
              <DecisionCard key={d.id} d={d} />
            ))
          )}
        </section>
      </main>
    </div>
  );
}
