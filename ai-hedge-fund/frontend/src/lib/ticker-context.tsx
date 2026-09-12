import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { TICKER_PATH_RE, stagePath, type DestinationKey } from "./flow";

/**
 * The active ticker, carried across the app.
 *
 * Without this every screen is an island: you research a name, form a view, and
 * then retype the symbol to size it, again to check the book, again to backtest
 * it. The work is one continuous thought about one company, and the interface
 * should not keep asking which company you meant.
 *
 * The URL stays the source of truth — a route carrying a symbol wins, so links
 * and browser history keep working. This layer only remembers what the URL does
 * not say, and keeps a short list of recents so returning to a name is one
 * click rather than a search.
 */

const STORAGE_KEY = "mj.ticker";
const RECENTS_KEY = "mj.ticker.recents";
const MAX_RECENTS = 8;

/**
 * The stages themselves live in `lib/flow`, which is the single list the rail,
 * the router and this provider all read. Keeping a second copy here is what let
 * the nav and the ticker bar disagree about what the flow was.
 */

type TickerContextValue = {
  ticker: string | null;
  recents: string[];
  /** Set the active ticker without navigating. */
  setTicker: (t: string | null) => void;
  /** Set it and move to the equivalent stage for that name. */
  goTo: (t: string, stage?: DestinationKey) => void;
  clear: () => void;
};

const TickerContext = createContext<TickerContextValue | null>(null);

function readRecents(): string[] {
  try {
    const raw = localStorage.getItem(RECENTS_KEY);
    return raw ? (JSON.parse(raw) as string[]).slice(0, MAX_RECENTS) : [];
  } catch {
    return [];
  }
}

/** Pull a symbol out of the path for any stage route carrying one. */
function tickerFromPath(pathname: string): string | null {
  const m = pathname.match(TICKER_PATH_RE);
  return m ? decodeURIComponent(m[2]).toUpperCase() : null;
}

export function TickerProvider({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();

  const [stored, setStored] = useState<string | null>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  });
  const [recents, setRecents] = useState<string[]>(readRecents);

  const fromUrl = tickerFromPath(location.pathname);
  // A symbol in the URL is explicit intent and outranks whatever was remembered.
  const ticker = fromUrl ?? stored;

  const remember = useCallback((t: string) => {
    setRecents((prev) => {
      const next = [t, ...prev.filter((x) => x !== t)].slice(0, MAX_RECENTS);
      try {
        localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
      } catch {
        /* a full or blocked store is not worth failing navigation over */
      }
      return next;
    });
  }, []);

  useEffect(() => {
    if (!fromUrl) return;
    setStored(fromUrl);
    try {
      localStorage.setItem(STORAGE_KEY, fromUrl);
    } catch {
      /* ignore */
    }
    remember(fromUrl);
  }, [fromUrl, remember]);

  const setTicker = useCallback(
    (t: string | null) => {
      const clean = t?.trim().toUpperCase() || null;
      setStored(clean);
      try {
        if (clean) localStorage.setItem(STORAGE_KEY, clean);
        else localStorage.removeItem(STORAGE_KEY);
      } catch {
        /* ignore */
      }
      if (clean) remember(clean);
    },
    [remember]
  );

  const goTo = useCallback(
    (t: string, stage: DestinationKey = "story") => {
      const clean = t.trim().toUpperCase();
      if (!clean) return;
      setTicker(clean);
      navigate(stagePath(stage, clean));
    },
    [navigate, setTicker]
  );

  const clear = useCallback(() => setTicker(null), [setTicker]);

  const value = useMemo(
    () => ({ ticker, recents, setTicker, goTo, clear }),
    [ticker, recents, setTicker, goTo, clear]
  );

  return <TickerContext.Provider value={value}>{children}</TickerContext.Provider>;
}

export function useTicker(): TickerContextValue {
  const ctx = useContext(TickerContext);
  if (!ctx) {
    throw new Error("useTicker must be used inside a TickerProvider");
  }
  return ctx;
}
