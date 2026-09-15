import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

/**
 * Daylight or the studio dark.
 *
 * The app opens in daylight. That is a decision, not a default inherited from
 * the machine: this is a research tool people read for long stretches, and the
 * dark ground it used to open on made the numbers hard to pick out. Someone who
 * prefers the dark can say so, and then it is remembered.
 *
 * Three states rather than two, because "I have not chosen" is different from
 * "I chose light":
 *
 *   light  — stamped on <html>, wins over a dark OS setting
 *   dark   — stamped, wins over a light OS setting
 *   system — nothing stamped, so the CSS media query decides
 *
 * The theme is applied by stamping `data-theme` and letting `src/index.css`
 * redefine its palette tokens. No component reads this hook to pick a colour;
 * if one ever needs to, that is a sign a token is missing.
 */

export type Theme = "light" | "dark" | "system";

const STORAGE_KEY = "mj.theme";
const THEMES: readonly Theme[] = ["light", "dark", "system"];

function isTheme(v: unknown): v is Theme {
  return typeof v === "string" && (THEMES as readonly string[]).includes(v);
}

/** What the reader last chose, or daylight if they have not. */
export function storedTheme(): Theme {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return isTheme(raw) ? raw : "light";
  } catch {
    /* Private browsing and blocked site data both throw on access rather than
     * returning null, so the read cannot be left bare. */
    return "light";
  }
}

/**
 * Stamp the root element. Exported so `main.tsx` can call it before React
 * mounts — applying it in an effect instead would paint one frame of the wrong
 * theme, which is the flash every themed site has to design around.
 */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

type ThemeValue = {
  theme: Theme;
  /** What is actually on screen once `system` has been resolved. */
  resolved: "light" | "dark";
  setTheme: (t: Theme) => void;
  /** Cycle the control: whatever is showing, go to the other one. */
  toggle: () => void;
};

const ThemeContext = createContext<ThemeValue | null>(null);

function systemPrefersDark(): boolean {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch {
    return false;
  }
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(storedTheme);
  const [systemDark, setSystemDark] = useState(systemPrefersDark);

  // Track the OS preference so `system` re-resolves when the machine flips at
  // sunset, rather than staying on whatever it was when the tab opened.
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    applyTheme(t);
    try {
      localStorage.setItem(STORAGE_KEY, t);
    } catch {
      /* The choice still applies to this tab; it just will not be remembered. */
    }
  }, []);

  const resolved: "light" | "dark" =
    theme === "system" ? (systemDark ? "dark" : "light") : theme;

  // The control offers the opposite of what is on screen. Someone on `system`
  // who presses it gets an explicit choice, which is what pressing it means.
  const toggle = useCallback(
    () => setTheme(resolved === "dark" ? "light" : "dark"),
    [resolved, setTheme],
  );

  return (
    <ThemeContext.Provider value={{ theme, resolved, setTheme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside a ThemeProvider");
  return ctx;
}
