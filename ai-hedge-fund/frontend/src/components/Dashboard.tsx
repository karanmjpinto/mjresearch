import { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { ChatInput } from "./ChatInput";
import { AppNav } from "./AppNav";

export function Dashboard() {
  const navigate = useNavigate();
  const [watchGroup, setWatchGroup] = useState<string>("default");

  const watchlists = useQuery({ queryKey: ["watchlists"], queryFn: api.getWatchlists });
  const portfolio = useQuery({ queryKey: ["portfolio"], queryFn: api.getPortfolio, retry: false });
  const sectors = useQuery({
    queryKey: ["sector-performance"],
    queryFn: api.getSectorPerformance,
    retry: false,
  });
  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: api.getProviderStatus,
    retry: false,
  });

  const groupKeys = useMemo(
    () => (watchlists.data ? Object.keys(watchlists.data) : []),
    [watchlists.data],
  );

  useEffect(() => {
    if (groupKeys.length && !groupKeys.includes(watchGroup)) {
      setWatchGroup(groupKeys[0]!);
    }
  }, [groupKeys, watchGroup]);

  const handleSearch = (query: string) => {
    const ticker = query.replace(/^check\s+/i, "").trim().toUpperCase();
    if (ticker) navigate(`/research/${ticker}`);
  };

  const sectorData =
    sectors.data?.realtime ??
    sectors.data?.one_day ??
    sectors.data?.five_day ??
    [];
  const sectorLabel = sectors.data?.realtime
    ? "Real-time"
    : sectors.data?.one_day
      ? "1 Day"
      : "5 Day";

  const tickers = watchlists.data?.[watchGroup] ?? [];

  return (
    <div className="flex flex-col h-screen">
      <AppNav
        active="home"
        end={<span className="text-xs text-gray-600 font-mono">AI hedge fund</span>}
      />

      <div className="flex grow overflow-hidden">
        <aside className="w-72 border-r border-border p-4 flex flex-col gap-4 overflow-y-auto">
          {portfolio.data && (
            <div className="bg-surface-card rounded-xl p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Book value</p>
              <p className="text-2xl font-bold text-white font-mono">
                ${portfolio.data.total_value.toLocaleString()}
              </p>
              <a href="/portfolio" className="text-xs text-blue-400 hover:underline mt-2 inline-block">
                Manage portfolio →
              </a>
            </div>
          )}
          <div className="bg-surface-card rounded-xl p-4">
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Watchlists</p>
            <p className="text-xs text-gray-600 mb-2">
              Edit <span className="font-mono text-gray-500">config/watchlists.json</span>
            </p>
            {groupKeys.length > 0 ? (
              <select
                value={watchGroup}
                onChange={(e) => setWatchGroup(e.target.value)}
                className="w-full bg-surface-elevated border border-border rounded-lg px-2 py-1.5 text-sm text-white mb-3"
              >
                {groupKeys.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            ) : (
              <p className="text-sm text-gray-500">Loading…</p>
            )}
            <div className="flex flex-col gap-0.5 max-h-48 overflow-y-auto">
              {tickers.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => navigate(`/research/${t}`)}
                  className="text-left text-sm py-1.5 px-2 rounded hover:bg-surface-elevated text-gray-200 font-mono"
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {providers.data && (
            <div className="bg-surface-card rounded-xl p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Data providers</p>
              {providers.data.providers.map((p) => (
                <div key={p.name} className="flex items-center justify-between py-1 text-xs">
                  <span className="text-gray-400 capitalize">{p.name}</span>
                  <span className={p.available ? "text-accent-green" : "text-gray-600"}>
                    {p.available ? "Active" : "Off"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </aside>

        <main className="grow p-6 flex flex-col gap-6 overflow-y-auto">
          <div>
            <h1 className="text-2xl font-bold text-white mb-1">Research desk</h1>
            <p className="text-gray-500 text-sm">
              Look up a symbol for fundamentals, technicals, and context — data only, no trading.
            </p>
          </div>
          <ChatInput onSubmit={handleSearch} />
        </main>

        <aside className="w-72 border-l border-border p-4 overflow-y-auto flex flex-col gap-4">
          <div className="bg-surface-card rounded-xl p-4">
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Quick actions</p>
            <button
              type="button"
              onClick={() => navigate("/research")}
              className="w-full text-left text-sm text-gray-300 hover:text-white py-1.5"
            >
              Open research
            </button>
            <button
              type="button"
              onClick={() => navigate("/portfolio")}
              className="w-full text-left text-sm text-gray-300 hover:text-white py-1.5"
            >
              Portfolio &amp; trades
            </button>
          </div>

          {sectorData.length > 0 && (
            <div className="bg-surface-card rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-gray-500 uppercase tracking-wider">Sector performance</p>
                <span className="text-[10px] text-gray-600">{sectorLabel}</span>
              </div>
              {sectorData
                .sort((a, b) => b.change_pct - a.change_pct)
                .map((s) => (
                  <div key={s.sector} className="flex justify-between py-1 text-xs">
                    <span className="text-gray-400 truncate mr-2">{s.sector}</span>
                    <span
                      className={`font-mono ${
                        s.change_pct > 0
                          ? "text-accent-green"
                          : s.change_pct < 0
                            ? "text-accent-red"
                            : "text-gray-500"
                      }`}
                    >
                      {s.change_pct > 0 ? "+" : ""}
                      {s.change_pct.toFixed(2)}%
                    </span>
                  </div>
                ))}
              {sectors.data?.source && (
                <p className="text-[10px] text-gray-600 mt-2">{sectors.data.source}</p>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
