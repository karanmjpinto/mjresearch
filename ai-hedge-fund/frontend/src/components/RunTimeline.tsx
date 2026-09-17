import { useEffect, useRef, useState } from "react";

/**
 * How long this is going to take, and how far in it is.
 *
 * A local model thinking for half a minute with no feedback is
 * indistinguishable from a hung request, and the honest fix is not a fake
 * progress bar. Two things here are true rather than estimated:
 *
 *   - the elapsed seconds, counted client-side
 *   - what the run will do, listed in order, because the stages are known
 *     before it starts (one pass per investor, then the synthesis)
 *
 * What is NOT claimed is which stage it is currently on. The endpoint returns
 * one response at the end and streams nothing, so a moving highlight would be
 * an animation pretending to be telemetry. The list says what is coming; the
 * clock says how long it has been.
 *
 * The expectation — "usually about 24s" — is measured from this reader's own
 * completed runs rather than a number someone typed in, so it describes their
 * machine and their model. Until three runs exist it says nothing, because an
 * average of one is a coincidence.
 */

const STORE_KEY = "mj.runtimes";
const KEEP = 8; // enough to be a median, short enough to follow a model swap
const MIN_FOR_ESTIMATE = 3;

type Store = Record<string, number[]>;

function read(): Store {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    const v = raw ? JSON.parse(raw) : {};
    return v && typeof v === "object" ? (v as Store) : {};
  } catch {
    return {};
  }
}

/** Record a completed run, newest last, oldest dropped. */
export function recordRuntime(kind: string, seconds: number): void {
  if (!Number.isFinite(seconds) || seconds <= 0) return;
  try {
    const store = read();
    store[kind] = [...(store[kind] ?? []), Math.round(seconds)].slice(-KEEP);
    localStorage.setItem(STORE_KEY, JSON.stringify(store));
  } catch {
    /* Not remembering a duration is not worth failing a render over. */
  }
}

/**
 * The median, not the mean. One cold start where the model had to load from
 * disk is enough to drag an average somewhere no future run will ever land.
 */
export function expectedRuntime(kind: string): number | null {
  const runs = read()[kind] ?? [];
  if (runs.length < MIN_FOR_ESTIMATE) return null;
  const sorted = [...runs].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[mid]!
    : Math.round((sorted[mid - 1]! + sorted[mid]!) / 2);
}

function useElapsed(running: boolean): number {
  const [elapsed, setElapsed] = useState(0);
  const started = useRef<number | null>(null);

  useEffect(() => {
    if (!running) {
      started.current = null;
      setElapsed(0);
      return;
    }
    started.current = Date.now();
    setElapsed(0);
    const id = window.setInterval(() => {
      if (started.current != null) {
        setElapsed((Date.now() - started.current) / 1000);
      }
    }, 250);
    return () => window.clearInterval(id);
  }, [running]);

  return elapsed;
}

export type RunStage = { label: string; detail?: string };

type Props = {
  running: boolean;
  /** What the run does, in order. Known up front. */
  stages: RunStage[];
  /** Groups the timing history: a committee run and a single pass differ. */
  kind: string;
  /** Seconds the finished run actually took, once there is one. */
  completedIn?: number | null;
  error?: string | null;
};

export function RunTimeline({
  running,
  stages,
  kind,
  completedIn,
  error,
}: Props) {
  const elapsed = useElapsed(running);
  const expected = expectedRuntime(kind);

  // The clock is the live region, not the whole panel: announcing the stage
  // list again on every tick would read the same eight lines every quarter
  // second. `off` while idle so a finished run does not re-announce.
  const status = error
    ? `Failed after ${elapsed.toFixed(0)}s`
    : running
      ? `Running, ${elapsed.toFixed(0)} seconds elapsed`
      : completedIn != null
        ? `Done in ${completedIn.toFixed(1)} seconds`
        : "Not started";

  return (
    <section
      aria-label="Analysis run"
      className="border border-ink-line bg-ink-raised p-md shadow-elev-1"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-sm">
        <h3 className="font-display text-label uppercase tracking-label text-on-ink-faint">
          {error
            ? "Run failed"
            : running
              ? "Thinking"
              : completedIn != null
                ? "Done"
                : "Ready"}
        </h3>
        <p
          aria-live={running ? "polite" : "off"}
          aria-atomic="true"
          className={`font-display text-mark tabular ${
            error ? "text-oxide" : running ? "text-cadmium" : "text-on-ink-soft"
          }`}
        >
          {running
            ? `${elapsed.toFixed(0)}s`
            : completedIn != null
              ? `${completedIn.toFixed(1)}s`
              : expected != null
                ? `~${expected}s`
                : "—"}
        </p>
        <span className="sr-only">{status}</span>
      </div>

      <p className="mt-2xs max-w-measure text-body-xs text-on-ink-faint">
        {error
          ? error
          : running
            ? expected != null
              ? `Your last few runs took about ${expected}s. Nothing is wrong until this is well past that.`
              : "A local model, so this depends on your machine. The first few runs are the slowest."
            : completedIn != null
              ? "Every number below came from Python; the model chose which to compute and wrote the prose."
              : expected != null
                ? `Usually about ${expected}s on this machine.`
                : "Runs locally via Ollama. No API key, no data leaving the machine."}
      </p>

      {/* The stages are a manifest, not a progress bar. Nothing here moves,
       * because nothing reports back until the whole run returns. */}
      <ol className="mt-sm flex flex-col gap-2xs">
        {stages.map((s, i) => (
          <li key={`${s.label}-${i}`} className="flex items-baseline gap-sm">
            <span className="w-5 shrink-0 font-display text-label tabular text-on-ink-faint">
              {String(i + 1).padStart(2, "0")}
            </span>
            <span
              className={`font-display text-label ${
                completedIn != null ? "text-on-ink-soft" : "text-on-ink-faint"
              }`}
            >
              {s.label}
            </span>
            {s.detail && (
              <span className="min-w-0 truncate text-body-xs text-on-ink-faint">
                {s.detail}
              </span>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
