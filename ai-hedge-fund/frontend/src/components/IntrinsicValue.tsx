import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Intrinsic } from "@/lib/api";

/**
 * Intrinsic value as a distribution, with the cost of capital that produced it.
 *
 * The growth rate is asked for rather than guessed. It is the most
 * consequential driver and no data provider supplies a forecast, so inventing
 * one would be exactly the false confidence the range exists to replace — the
 * screen stays empty and says which number it is waiting for.
 *
 * Two warnings are surfaced rather than buried: how much of the value sits in
 * the terminal year, and the approximations the drivers rest on. A value that
 * is three-quarters terminal is a statement about perpetual growth, not about
 * the next decade.
 */

function Field({
  label,
  value,
  onChange,
  placeholder,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  hint: string;
}) {
  const id = `driver-${label.replace(/\s+/g, "-").toLowerCase()}`;
  return (
    <label htmlFor={id} className="flex flex-col gap-2xs">
      <span className="font-display text-label uppercase tracking-label text-on-ink-soft">
        {label}
      </span>
      <input
        id={id}
        value={value}
        inputMode="decimal"
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-[120px] border border-ink-line bg-ink px-sm py-1.5 font-display text-label text-bone outline-none transition-colors placeholder:text-on-ink-faint focus:border-cobalt"
      />
      <span className="text-body-xs text-on-ink-faint">{hint}</span>
    </label>
  );
}

function Histogram({
  bins,
  price,
}: {
  bins: { from: number; to: number; count: number }[];
  price: number | null;
}) {
  const peak = Math.max(...bins.map((b) => b.count), 1);
  const lo = bins[0]?.from ?? 0;
  const hi = bins[bins.length - 1]?.to ?? 1;
  const span = hi - lo || 1;
  const pricePct = price ? ((price - lo) / span) * 100 : null;
  const inside = pricePct !== null && pricePct >= 0 && pricePct <= 100;

  return (
    <div>
      <div className="relative flex h-28 items-end gap-px" aria-hidden>
        {bins.map((b) => (
          <div
            key={b.from}
            className={`flex-1 rounded-t ${
              price && b.to <= price ? "bg-on-ink-faint/40" : "bg-cobalt/50"
            }`}
            style={{ height: `${Math.max((b.count / peak) * 100, 1)}%` }}
            title={`${b.from.toFixed(0)}–${b.to.toFixed(0)}: ${b.count} runs`}
          />
        ))}
        {inside && (
          <div
            className="absolute inset-y-0 border-l border-dashed border-oxide"
            style={{ left: `${pricePct}%` }}
          />
        )}
      </div>
      <div className="mt-2xs flex justify-between font-display text-label text-on-ink-faint tabular">
        <span>{lo.toFixed(0)}</span>
        {!inside && price !== null && (
          <span className="text-oxide">
            price {price.toFixed(0)} — off the chart
          </span>
        )}
        <span>{hi.toFixed(0)}</span>
      </div>
    </div>
  );
}

export function IntrinsicValue({ ticker }: { ticker: string }) {
  const [growth, setGrowth] = useState("");
  const [coverage, setCoverage] = useState("");
  const [applied, setApplied] = useState<{ growth: string; coverage: string }>({
    growth: "",
    coverage: "",
  });

  const q = useQuery({
    queryKey: ["intrinsic", ticker, applied.growth, applied.coverage],
    queryFn: () =>
      api.getIntrinsic(ticker, {
        revenue_growth: applied.growth || undefined,
        interest_coverage: applied.coverage || undefined,
        runs: 4000,
      }),
    enabled: Boolean(ticker),
  });

  const controls = (
    <form
      className="flex flex-wrap items-end gap-md"
      onSubmit={(e) => {
        e.preventDefault();
        setApplied({ growth, coverage });
      }}
    >
      <Field
        label="Revenue growth"
        value={growth}
        onChange={setGrowth}
        placeholder="0.06"
        hint="Your view, as a decimal. Nothing supplies a forecast."
      />
      <Field
        label="Interest cover"
        value={coverage}
        onChange={setCoverage}
        placeholder="30"
        hint="Operating profit over interest. Sets the cost of debt."
      />
      <button
        type="submit"
        className="border border-ink-line px-sm py-1.5 font-display text-label uppercase tracking-label text-on-ink-soft transition-colors hover:border-cobalt hover:text-bone"
      >
        Value it
      </button>
    </form>
  );

  const d: Intrinsic | undefined = q.data;

  return (
    <section
      className="flex flex-col gap-md"
      aria-label={`Intrinsic value for ${ticker}`}
    >
      <div className="flex flex-col gap-2xs">
        <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
          Intrinsic value · $ per share
        </span>
        {controls}
      </div>

      {q.isLoading && (
        <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
          Running the model…
        </p>
      )}

      {q.isError && (
        <p className="text-body-sm text-oxide">
          The model could not be run for this name.
        </p>
      )}

      {d && !d.available && (
        <div className="flex flex-col gap-xs">
          <p className="text-body-sm text-on-ink-soft">{d.reason}.</p>
          <p className="text-body-sm text-cadmium">
            Waiting on: {d.missing.join(", ")}. Fill the boxes above and press
            Value it.
          </p>
          {d.cost_of_capital.wacc_pct !== null && (
            <p className="text-body-xs text-on-ink-faint tabular">
              Cost of capital is already known: {d.cost_of_capital.wacc_pct}%.
            </p>
          )}
        </div>
      )}

      {d && d.available && (
        <>
          <p className="text-body-sm text-on-ink-soft">
            <span className="tabular text-on-ink">
              {d.distribution.percentiles.p10?.toFixed(2)} –{" "}
              {d.distribution.percentiles.p90?.toFixed(2)}
            </span>{" "}
            across {d.distribution.runs.toLocaleString()} runs, base case{" "}
            <span className="tabular text-on-ink">
              {d.base_case.value_per_share.toFixed(2)}
            </span>
            {d.price !== null && (
              <>
                , against a price of{" "}
                <span className="tabular text-cadmium">
                  {d.price.toFixed(2)}
                </span>
              </>
            )}
            {typeof d.distribution.probability_value_above_price ===
              "number" && (
              <>
                . Chance the value beats the price:{" "}
                <span className="tabular text-on-ink">
                  {(d.distribution.probability_value_above_price * 100).toFixed(
                    0,
                  )}
                  %
                </span>
              </>
            )}
          </p>

          <Histogram bins={d.distribution.histogram} price={d.price} />

          {d.base_case.terminal_share_of_value > 0.6 && (
            <p className="max-w-measure border-l-2 border-cadmium pl-sm text-body-xs text-on-ink-soft">
              {(d.base_case.terminal_share_of_value * 100).toFixed(0)}% of this
              value sits in the terminal year, so the answer is mostly a
              statement about growth in perpetuity rather than about the next
              decade.
            </p>
          )}

          <div className="flex flex-col gap-2xs">
            <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
              Cost of capital ·{" "}
              {d.cost_of_capital.wacc_pct ??
                d.cost_of_capital.cost_of_equity_pct}
              %
            </span>
            <ul className="flex flex-col gap-2xs">
              {d.cost_of_capital.steps.map((s) => (
                <li
                  key={s}
                  className="font-display text-label text-on-ink-soft tabular"
                >
                  {s}
                </li>
              ))}
            </ul>
          </div>

          {(d.driver_notes.length > 0 ||
            d.cost_of_capital.missing.length > 0) && (
            <div className="flex flex-col gap-2xs">
              <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
                What this rests on
              </span>
              <ul className="flex flex-col gap-2xs">
                {[...d.cost_of_capital.missing, ...d.driver_notes].map((n) => (
                  <li
                    key={n}
                    className="max-w-measure text-body-xs text-on-ink-faint"
                  >
                    {n}
                  </li>
                ))}
                <li className="max-w-measure text-body-xs text-on-ink-faint">
                  {d.distribution.independence_note}; seed {d.distribution.seed}
                  , so the same inputs give the same range.
                </li>
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}
