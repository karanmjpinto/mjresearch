import { Link } from "react-router-dom";

export type AppNavActive =
  | "home"
  | "plan"
  | "research"
  | "screeners"
  | "optimize"
  | "portfolio";

const link = "text-sm text-gray-500 transition-colors hover:text-gray-300";
const activeLink = "text-sm font-medium text-blue-400";

type Props = {
  active: AppNavActive;
  /** Optional right side: e.g. tagline (`AI hedge fund`) or wide search (`ChatInput`). */
  end?: React.ReactNode;
};

export function AppNav({ active, end }: Props) {
  return (
    <nav className="flex items-center justify-between px-6 py-3 border-b border-border">
      <div className="flex items-center gap-6">
        <Link to="/" className="text-lg font-bold tracking-tight text-white">
          MJ
        </Link>
        <Link to="/dashboard" className={active === "home" ? activeLink : link}>
          Dashboard
        </Link>
        <Link to="/plan" className={active === "plan" ? activeLink : link}>
          Plan
        </Link>
        <Link to="/research" className={active === "research" ? activeLink : link}>
          Research
        </Link>
        <Link to="/screeners" className={active === "screeners" ? activeLink : link}>
          Screeners
        </Link>
        <Link to="/optimize" className={active === "optimize" ? activeLink : link}>
          Optimize
        </Link>
        <Link to="/portfolio" className={active === "portfolio" ? activeLink : link}>
          Portfolio
        </Link>
      </div>
      {end != null && <div className="hidden sm:flex shrink-0">{end}</div>}
    </nav>
  );
}
