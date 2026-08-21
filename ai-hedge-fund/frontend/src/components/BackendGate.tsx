import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";

/**
 * Explains an unreachable backend instead of letting every panel fail alone.
 *
 * The published site is static, so the app routes have no API behind them.
 * Without this the screens render a dozen separate errors and look broken,
 * when the real situation is simply that this part needs to run locally.
 */
export function BackendGate({ children }: { children: React.ReactNode }) {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    retry: false,
    staleTime: 30_000,
  });

  if (health.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-ink">
        <p className="font-display text-[12px] uppercase tracking-[0.2em] text-on-ink-faint">
          Connecting…
        </p>
      </div>
    );
  }

  if (health.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-ink px-6">
        <div className="max-w-lg">
          <span className="inline-block bg-cadmium px-sm py-2xs font-display text-[11px] uppercase tracking-[0.18em] text-ink">
            Backend not reachable
          </span>
          <h1 className="mt-lg font-display text-display-sm leading-tight tracking-tight text-bone">
            This part runs on your machine
          </h1>
          <p className="mt-md text-[15px] leading-relaxed text-on-ink-soft">
            The app needs the local API, your SQLite portfolio and Ollama — none of which are
            hosted. Nothing about your book or your model leaves your computer, which is the
            point, but it does mean the published site can only show the overview.
          </p>
          <div className="mt-lg overflow-x-auto border border-ink-line bg-ink-raised p-md text-left">
            <pre className="font-display text-[12px] leading-relaxed text-cadmium">
{`cd ai-hedge-fund
uv run uvicorn hedge_fund.api.main:app --reload
cd frontend && npm run dev`}
            </pre>
          </div>
          <div className="mt-lg flex flex-wrap items-center gap-sm font-display text-[11px] uppercase tracking-[0.14em]">
            <Link
              to="/"
              className="border-2 border-ink-line px-5 py-3 text-on-ink transition-colors hover:border-bone hover:text-bone"
            >
              Back to overview
            </Link>
            <a
              href="https://github.com/karanmjpinto/ai-hedge-fund#quick-start"
              target="_blank"
              rel="noreferrer"
              className="bg-oxide px-5 py-3 text-bone transition-colors hover:bg-cadmium hover:text-ink"
            >
              Setup guide
            </a>
          </div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
