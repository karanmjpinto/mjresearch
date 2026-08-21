import { Link } from "react-router-dom";

export type AppNavActive =
  | "home"
  | "plan"
  | "research"
  | "screeners"
  | "optimize"
  | "portfolio"
  | "autoresearch"
  | "setup";

/**
 * Application chrome. Labels are set in the display face at small sizes with
 * wide tracking — the pixel face is legible as a label and unreadable as prose,
 * so it is used only where it works.
 *
 * The active item is marked with a painted underline rather than a colour
 * swap, so position is readable at a glance without hunting for a hue.
 */
const NAV: { to: string; key: AppNavActive; label: string }[] = [
  { to: "/dashboard", key: "home", label: "Dashboard" },
  { to: "/plan", key: "plan", label: "Plan" },
  { to: "/research", key: "research", label: "Research" },
  { to: "/screeners", key: "screeners", label: "Screeners" },
  { to: "/optimize", key: "optimize", label: "Optimize" },
  { to: "/portfolio", key: "portfolio", label: "Portfolio" },
  { to: "/autoresearch", key: "autoresearch", label: "Autoresearch" },
  { to: "/setup", key: "setup", label: "Setup" },
];

type Props = {
  active: AppNavActive;
  /** Optional right side: e.g. tagline or a wide search input. */
  end?: React.ReactNode;
};

export function AppNav({ active, end }: Props) {
  return (
    <nav className="sticky top-0 z-30 border-b border-ink-line bg-ink/95 backdrop-blur-sm">
      <div className="flex items-center justify-between gap-md px-lg py-sm">
        <div className="flex min-w-0 items-center gap-lg">
          <Link
            to="/"
            className="font-display text-[15px] tracking-[0.14em] text-bone transition-colors hover:text-oxide"
            title="Back to overview"
          >
            MJ
          </Link>
          <div className="scrollbar-none flex min-w-0 items-center gap-md overflow-x-auto">
            {NAV.map((item) => {
              const on = active === item.key;
              return (
                <Link
                  key={item.key}
                  to={item.to}
                  className={`relative shrink-0 py-1 font-display text-[11px] uppercase tracking-[0.14em] transition-colors ${
                    on ? "text-bone" : "text-on-ink-faint hover:text-on-ink"
                  }`}
                >
                  {item.label}
                  {on && (
                    <span
                      aria-hidden
                      className="absolute -bottom-[9px] left-0 h-[2px] w-full bg-oxide"
                    />
                  )}
                </Link>
              );
            })}
          </div>
        </div>
        {end != null && <div className="hidden shrink-0 sm:flex">{end}</div>}
      </div>
    </nav>
  );
}
