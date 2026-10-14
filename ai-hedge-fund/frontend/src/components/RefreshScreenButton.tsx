import { useEffect, useRef } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";

/**
 * Run a screen from the page that shows it.
 *
 * The refresh was a shell command printed in three places on this screen,
 * which is a fine instruction and a poor affordance: it assumes the reader
 * is at a terminal, in the repo, with the environment installed — and on a
 * phone, which this app is built to be read on, it assumes something that
 * cannot happen at all.
 *
 * The command stays. It is still the honest answer for a universe you want
 * to run unattended, it is what CI and cron use, and removing it would
 * leave no way to see what the button actually does. This is the same
 * action, reachable by thumb.
 *
 * PROGRESS, NOT A SPINNER. A screen is several seconds per name against the
 * data provider, so a 600-name universe is minutes, not moments. A spinner
 * over that is indistinguishable from a hang, and the backend already
 * reports `done` and `total` precisely because the client that started a
 * run may not be the one watching it. Polling stops when the job does.
 */
export function RefreshScreenButton({
  screen,
  universe,
  onDone,
}: {
  screen: string;
  universe: string;
  /** Invalidate whatever the caller is showing, once the cache is rewritten. */
  onDone?: () => void;
}) {
  const qc = useQueryClient();

  const jobs = useQuery({
    queryKey: ["screen-jobs"],
    queryFn: api.getScreenJobs,
    /* Only while something is running. An idle desk should not poll a
     * backend once a second for the rest of the session — and the answer
     * cannot change without this component being the thing that changed
     * it, or another tab doing the same, which the next poll catches. */
    refetchInterval: (q) => (q.state.data?.busy ? 1500 : false),
    retry: false,
  });

  const mine = jobs.data?.running.find(
    (j) => j.screen === screen && j.universe === universe,
  );

  const start = useMutation({
    mutationFn: () => api.startScreenJob(screen, universe),
    onSuccess: () => {
      // Begin polling immediately rather than waiting for the next tick.
      void qc.invalidateQueries({ queryKey: ["screen-jobs"] });
    },
  });

  /* The run finished between two polls: the job has left `running` and the
   * cache on disk is now the answer. Nothing else will tell the page to
   * re-read it, so this does.
   *
   * In an effect, not in the render body. Calling `reset()` and
   * `invalidateQueries` while rendering schedules a state update from
   * inside a render, which React either warns about or loops on depending
   * on timing — and the loop is the bad case, because each invalidate
   * re-renders and re-triggers the condition. The transition is detected by
   * comparing against the previous value rather than by reading the current
   * one, so it fires once on the edge instead of on every frame after it. */
  const wasRunning = useRef(false);
  useEffect(() => {
    const isRunning = Boolean(mine);
    if (wasRunning.current && !isRunning) {
      start.reset();
      void qc.invalidateQueries({ queryKey: ["screen-results"] });
      onDone?.();
    }
    wasRunning.current = isRunning;
  }, [mine, qc, start, onDone]);

  const busyElsewhere = Boolean(jobs.data?.busy && !mine);
  const running = Boolean(mine);
  const pct =
    mine && mine.total > 0 ? Math.round((mine.done / mine.total) * 100) : 0;

  return (
    <span className="inline-flex flex-wrap items-center gap-xs">
      <button
        type="button"
        onClick={() => start.mutate()}
        disabled={running || start.isPending || busyElsewhere}
        /* `title` carries the reason it is disabled. A greyed control with
         * no explanation is the most common way a working feature reads as
         * a broken one. */
        title={
          busyElsewhere
            ? "Another screen is running — they share one data provider and one rate limit"
            : running
              ? "This screen is running"
              : `Recompute ${screen} over ${universe}`
        }
        className="border border-ink-line px-sm py-1.5 font-display text-label uppercase tracking-label text-on-ink-soft transition-colors hover:border-cobalt hover:text-bone disabled:cursor-not-allowed disabled:border-ink-line disabled:text-on-ink-faint disabled:hover:text-on-ink-faint"
      >
        {running ? "Running" : start.isPending ? "Starting…" : "Refresh"}
      </button>

      {running && mine && (
        <span className="inline-flex items-center gap-xs">
          {/* A real bar, because `done/total` is known. */}
          <span
            className="inline-block h-1.5 w-24 bg-ink-line"
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${screen} progress`}
          >
            <span
              className="block h-full bg-cadmium transition-[width] duration-500"
              style={{ width: `${pct}%` }}
            />
          </span>
          <span className="tabular font-display text-label text-on-ink-faint">
            {mine.done}/{mine.total}
          </span>
        </span>
      )}

      {mine?.error && (
        <span className="text-sm text-oxide">{mine.error.slice(0, 120)}</span>
      )}

      {start.isError && (
        <span className="text-sm text-oxide">
          Could not start — the backend has no runner for this screen, or one
          is already running on this universe.
        </span>
      )}

      {busyElsewhere && !running && (
        <span className="text-sm text-on-ink-faint">
          Another screen is running.
        </span>
      )}
    </span>
  );
}
