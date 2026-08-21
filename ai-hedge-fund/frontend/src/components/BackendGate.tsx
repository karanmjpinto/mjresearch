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
      <div className="flex min-h-screen items-center justify-center bg-surface">
        <p className="text-sm text-gray-600">Connecting…</p>
      </div>
    );
  }

  if (health.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface px-6">
        <div className="max-w-lg text-center">
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-accent-yellow/80">
            Backend not reachable
          </p>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-white">
            This part runs on your machine
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-gray-400">
            The app needs the local API, your SQLite portfolio and Ollama — none of which are
            hosted. Nothing about your book or your model leaves your computer, which is the
            point, but it does mean the published site can only show the overview.
          </p>
          <div className="mt-6 overflow-x-auto rounded-lg border border-border bg-surface-card p-4 text-left">
            <pre className="font-mono text-xs leading-relaxed text-gray-400">
{`cd ai-hedge-fund
uv run uvicorn hedge_fund.api.main:app --reload
cd frontend && npm run dev`}
            </pre>
          </div>
          <div className="mt-6 flex items-center justify-center gap-3">
            <Link
              to="/"
              className="rounded-lg border border-border-light px-4 py-2 text-sm text-gray-300 transition-colors hover:border-gray-600 hover:text-white"
            >
              Back to overview
            </Link>
            <a
              href="https://github.com/karanmjpinto/ai-hedge-fund#quick-start"
              target="_blank"
              rel="noreferrer"
              className="rounded-lg bg-accent-blue px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500"
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
