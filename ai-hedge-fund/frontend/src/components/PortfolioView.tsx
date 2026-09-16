import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { AppNav } from "./AppNav";

export default function PortfolioView() {
  const qc = useQueryClient();
  const portfolio = useQuery({
    queryKey: ["portfolio"],
    queryFn: api.getPortfolio,
  });
  const risk = useQuery({
    queryKey: ["risk"],
    queryFn: api.getRisk,
    retry: false,
  });
  const txns = useQuery({
    queryKey: ["transactions"],
    queryFn: () => api.getTransactions(80),
  });

  const [buy, setBuy] = useState({
    ticker: "",
    shares: "",
    price: "",
    fee: "0",
  });
  const [sell, setSell] = useState({
    ticker: "",
    shares: "",
    price: "",
    fee: "0",
  });
  const [cash, setCash] = useState({ amount: "", deposit: true });
  const [split, setSplit] = useState({ ticker: "", ratio: "" });
  const [div, setDiv] = useState({ ticker: "", perShare: "" });
  const [edit, setEdit] = useState({ ticker: "", shares: "", avgCost: "" });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["portfolio"] });
    void qc.invalidateQueries({ queryKey: ["risk"] });
    void qc.invalidateQueries({ queryKey: ["transactions"] });
  };

  const mBuy = useMutation({
    mutationFn: () =>
      api.portfolioBuy({
        ticker: buy.ticker.toUpperCase(),
        shares: Number(buy.shares),
        price_per_share: Number(buy.price),
        fee: Number(buy.fee) || 0,
      }),
    onSuccess: () => {
      invalidate();
      setBuy({ ticker: "", shares: "", price: "", fee: "0" });
    },
  });

  const mSell = useMutation({
    mutationFn: () =>
      api.portfolioSell({
        ticker: sell.ticker.toUpperCase(),
        shares: Number(sell.shares),
        price_per_share: Number(sell.price),
        fee: Number(sell.fee) || 0,
      }),
    onSuccess: () => {
      invalidate();
      setSell({ ticker: "", shares: "", price: "", fee: "0" });
    },
  });

  const mCash = useMutation({
    mutationFn: () =>
      cash.deposit
        ? api.portfolioDeposit({ amount: Number(cash.amount) })
        : api.portfolioWithdraw({ amount: Number(cash.amount) }),
    onSuccess: () => {
      invalidate();
      setCash({ ...cash, amount: "" });
    },
  });

  const mSplit = useMutation({
    mutationFn: () =>
      api.portfolioSplit({
        ticker: split.ticker.toUpperCase(),
        ratio: Number(split.ratio),
      }),
    onSuccess: () => {
      invalidate();
      setSplit({ ticker: "", ratio: "" });
    },
  });

  const mDiv = useMutation({
    mutationFn: () =>
      api.portfolioDividend({
        ticker: div.ticker.toUpperCase(),
        dividend_per_share: Number(div.perShare),
      }),
    onSuccess: () => {
      invalidate();
      setDiv({ ticker: "", perShare: "" });
    },
  });

  const mPatch = useMutation({
    mutationFn: () =>
      api.patchHolding(edit.ticker.toUpperCase(), {
        shares: edit.shares ? Number(edit.shares) : undefined,
        avg_cost: edit.avgCost ? Number(edit.avgCost) : undefined,
      }),
    onSuccess: () => {
      invalidate();
      setEdit({ ticker: "", shares: "", avgCost: "" });
    },
  });

  const p = portfolio.data;

  return (
    <div className="flex flex-col min-h-screen">
      <AppNav active="portfolio" />

      <div className="p-6 max-w-7xl mx-auto w-full flex flex-col gap-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Portfolio</h1>
          <p className="text-gray-500 text-sm">
            SQLite-backed book — trades, cash, splits, and dividends. Risk uses
            value-weighted returns.
          </p>
        </div>

        {p && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat
              label="Total value"
              value={`$${p.total_value.toLocaleString()}`}
            />
            <Stat
              label="Cash"
              value={`$${p.cash.toLocaleString()} (${p.cash_pct.toFixed(1)}%)`}
            />
            <Stat label="Benchmark" value={p.benchmark ?? "—"} />
            <Stat label="Positions" value={String(p.holdings.length)} />
          </div>
        )}

        {risk.data && !("error" in risk.data) && (
          <div className="bg-surface-card rounded-xl p-4 grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat
              label="VaR 95% (daily)"
              value={`${risk.data.var_95_daily}%`}
            />
            <Stat label="CVaR 95%" value={`${risk.data.cvar_95_daily}%`} />
            <Stat label="Sharpe" value={String(risk.data.sharpe_ratio)} />
            <Stat
              label="Max drawdown"
              value={`${risk.data.max_drawdown_pct}%`}
            />
            <p className="col-span-full text-xs text-gray-600">
              {String(risk.data.method ?? "")} ·{" "}
              {String(risk.data.observations ?? "")} days
            </p>
          </div>
        )}
        {"error" in (risk.data ?? {}) && (
          <p className="text-sm text-amber-500">
            {(risk.data as { error: string }).error}
          </p>
        )}

        <div className="bg-surface-card rounded-xl p-4 overflow-x-auto">
          <h2 className="text-white font-semibold mb-3">Holdings</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 text-left">
                <th className="pb-2">Ticker</th>
                <th className="pb-2 text-right">Shares</th>
                <th className="pb-2 text-right">Avg cost</th>
                <th className="pb-2 text-right">Price</th>
                <th className="pb-2 text-right">Value</th>
                <th className="pb-2 text-right">P&amp;L %</th>
                <th className="pb-2 text-right">Weight</th>
              </tr>
            </thead>
            <tbody>
              {(p?.holdings ?? []).map((h) => (
                <tr key={h.ticker} className="border-t border-border">
                  <td className="py-2 text-white font-medium">{h.ticker}</td>
                  <td className="py-2 text-right font-mono">{h.shares}</td>
                  <td className="py-2 text-right font-mono">{h.avg_cost}</td>
                  <td className="py-2 text-right font-mono">
                    {h.current_price}
                  </td>
                  <td className="py-2 text-right font-mono">
                    {h.market_value.toLocaleString()}
                  </td>
                  <td
                    className={`py-2 text-right font-mono ${
                      h.pnl_pct >= 0 ? "text-accent-green" : "text-accent-red"
                    }`}
                  >
                    {h.pnl_pct >= 0 ? "+" : ""}
                    {h.pnl_pct}%
                  </td>
                  <td className="py-2 text-right font-mono text-gray-400">
                    {h.weight_pct}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          <FormCard title="Buy">
            <input
              className="w-full bg-surface-elevated border border-border rounded px-2 py-1 text-sm mb-2"
              placeholder="Ticker"
              value={buy.ticker}
              onChange={(e) => setBuy({ ...buy, ticker: e.target.value })}
            />
            <input
              className="w-full bg-surface-elevated border border-border rounded px-2 py-1 text-sm mb-2"
              placeholder="Shares"
              value={buy.shares}
              onChange={(e) => setBuy({ ...buy, shares: e.target.value })}
            />
            <input
              className="w-full bg-surface-elevated border border-border rounded px-2 py-1 text-sm mb-2"
              placeholder="Price / share"
              value={buy.price}
              onChange={(e) => setBuy({ ...buy, price: e.target.value })}
            />
            <input
              className="w-full bg-surface-elevated border border-border rounded px-2 py-1 text-sm mb-2"
              placeholder="Fee"
              value={buy.fee}
              onChange={(e) => setBuy({ ...buy, fee: e.target.value })}
            />
            <button
              type="button"
              onClick={() => mBuy.mutate()}
              disabled={mBuy.isPending}
              className="w-full py-2 bg-blue-600 rounded text-sm text-white"
            >
              Buy
            </button>
            {mBuy.isError && (
              <p className="text-xs text-red-400 mt-1">
                {(mBuy.error as Error).message}
              </p>
            )}
          </FormCard>

          <FormCard title="Sell">
            <input
              className="w-full bg-surface-elevated border border-border rounded px-2 py-1 text-sm mb-2"
              placeholder="Ticker"
              value={sell.ticker}
              onChange={(e) => setSell({ ...sell, ticker: e.target.value })}
            />
            <input
              className="w-full bg-surface-elevated border border-border rounded px-2 py-1 text-sm mb-2"
              placeholder="Shares"
              value={sell.shares}
              onChange={(e) => setSell({ ...sell, shares: e.target.value })}
            />
            <input
              className="w-full bg-surface-elevated border border-border rounded px-2 py-1 text-sm mb-2"
              placeholder="Price / share"
              value={sell.price}
              onChange={(e) => setSell({ ...sell, price: e.target.value })}
            />
            <input
              className="w-full bg-surface-elevated border border-border rounded px-2 py-1 text-sm mb-2"
              placeholder="Fee"
              value={sell.fee}
              onChange={(e) => setSell({ ...sell, fee: e.target.value })}
            />
            <button
              type="button"
              onClick={() => mSell.mutate()}
              disabled={mSell.isPending}
              className="w-full py-2 bg-amber-700 rounded text-sm text-white"
            >
              Sell
            </button>
            {mSell.isError && (
              <p className="text-xs text-red-400 mt-1">
                {(mSell.error as Error).message}
              </p>
            )}
          </FormCard>

          <FormCard title="Cash">
            <label className="flex items-center gap-2 text-sm text-gray-400 mb-2">
              <input
                type="checkbox"
                checked={cash.deposit}
                onChange={(e) =>
                  setCash({ ...cash, deposit: e.target.checked })
                }
              />
              Deposit (unchecked = withdraw)
            </label>
            <input
              className="w-full bg-surface-elevated border border-border rounded px-2 py-1 text-sm mb-2"
              placeholder="Amount"
              value={cash.amount}
              onChange={(e) => setCash({ ...cash, amount: e.target.value })}
            />
            <button
              type="button"
              onClick={() => mCash.mutate()}
              disabled={mCash.isPending}
              className="w-full py-2 bg-slate-600 rounded text-sm text-white"
            >
              Apply
            </button>
            {mCash.isError && (
              <p className="text-xs text-red-400 mt-1">
                {(mCash.error as Error).message}
              </p>
            )}
          </FormCard>

          <FormCard title="Stock split (forward ratio)">
            <p className="text-xs text-gray-600 mb-2">
              e.g. 4 for a 4:1 split — multiplies shares, divides avg cost.
            </p>
            <input
              className="w-full bg-surface-elevated border border-border rounded px-2 py-1 text-sm mb-2"
              placeholder="Ticker"
              value={split.ticker}
              onChange={(e) => setSplit({ ...split, ticker: e.target.value })}
            />
            <input
              className="w-full bg-surface-elevated border border-border rounded px-2 py-1 text-sm mb-2"
              placeholder="Ratio"
              value={split.ratio}
              onChange={(e) => setSplit({ ...split, ratio: e.target.value })}
            />
            <button
              type="button"
              onClick={() => mSplit.mutate()}
              disabled={mSplit.isPending}
              className="w-full py-2 bg-slate-600 rounded text-sm text-white"
            >
              Apply split
            </button>
            {mSplit.isError && (
              <p className="text-xs text-red-400 mt-1">
                {(mSplit.error as Error).message}
              </p>
            )}
          </FormCard>

          <FormCard title="Cash dividend">
            <input
              className="w-full bg-surface-elevated border border-border rounded px-2 py-1 text-sm mb-2"
              placeholder="Ticker"
              value={div.ticker}
              onChange={(e) => setDiv({ ...div, ticker: e.target.value })}
            />
            <input
              className="w-full bg-surface-elevated border border-border rounded px-2 py-1 text-sm mb-2"
              placeholder="Dividend per share"
              value={div.perShare}
              onChange={(e) => setDiv({ ...div, perShare: e.target.value })}
            />
            <button
              type="button"
              onClick={() => mDiv.mutate()}
              disabled={mDiv.isPending}
              className="w-full py-2 bg-slate-600 rounded text-sm text-white"
            >
              Record dividend
            </button>
            {mDiv.isError && (
              <p className="text-xs text-red-400 mt-1">
                {(mDiv.error as Error).message}
              </p>
            )}
          </FormCard>

          <FormCard title="Manual holding edit">
            <input
              className="w-full bg-surface-elevated border border-border rounded px-2 py-1 text-sm mb-2"
              placeholder="Ticker"
              value={edit.ticker}
              onChange={(e) => setEdit({ ...edit, ticker: e.target.value })}
            />
            <input
              className="w-full bg-surface-elevated border border-border rounded px-2 py-1 text-sm mb-2"
              placeholder="Shares (optional)"
              value={edit.shares}
              onChange={(e) => setEdit({ ...edit, shares: e.target.value })}
            />
            <input
              className="w-full bg-surface-elevated border border-border rounded px-2 py-1 text-sm mb-2"
              placeholder="Avg cost (optional)"
              value={edit.avgCost}
              onChange={(e) => setEdit({ ...edit, avgCost: e.target.value })}
            />
            <button
              type="button"
              onClick={() => mPatch.mutate()}
              disabled={mPatch.isPending}
              className="w-full py-2 bg-slate-600 rounded text-sm text-white"
            >
              Patch
            </button>
            {mPatch.isError && (
              <p className="text-xs text-red-400 mt-1">
                {(mPatch.error as Error).message}
              </p>
            )}
          </FormCard>
        </div>

        <div className="bg-surface-card rounded-xl p-4">
          <h2 className="text-white font-semibold mb-3">Recent transactions</h2>
          <div className="max-h-64 overflow-y-auto text-xs font-mono space-y-1">
            {(txns.data?.transactions ?? []).map((t) => (
              <div
                key={t.id}
                className="flex justify-between border-b border-border/50 py-1"
              >
                <span className="text-gray-400">
                  {t.executed_at.slice(0, 19)} {t.txn_type} {t.ticker ?? ""}
                </span>
                <span
                  className={
                    t.cash_delta >= 0 ? "text-accent-green" : "text-accent-red"
                  }
                >
                  {t.cash_delta >= 0 ? "+" : ""}
                  {t.cash_delta.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-surface-card rounded-xl p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
      <p className="text-lg font-bold text-white font-mono">{value}</p>
    </div>
  );
}

function FormCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="bg-surface-card rounded-xl p-4">
      <h3 className="text-white font-medium mb-2">{title}</h3>
      {children}
    </div>
  );
}
