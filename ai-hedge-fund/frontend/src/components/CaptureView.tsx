import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { AppNav } from "./AppNav";
import { api } from "@/lib/api";
import { useTicker } from "@/lib/ticker-context";

/**
 * Capture — a decision, recorded in the time it takes to have one.
 *
 * The one screen here built for a phone first. Everything else in this app is
 * a reading surface that has to survive being narrow; this is the opposite,
 * and it is the only job a phone is genuinely *better* at than a laptop. The
 * thought arrives on a walk, in a meeting, reading a filing on the train. By
 * the time a laptop is open it has been reworded into something more
 * defensible than it was, which is exactly the thing you did not want to
 * record.
 *
 * So: one screen, no navigation, five buttons and a box. The ticker prefills
 * from whatever you were last looking at.
 *
 * `pass` is on the same row as `buy` on purpose, and is the reason this screen
 * is worth having at all. A rejection with a reason, written at the moment of
 * rejecting, is the highest-compounding record a research desk keeps — it is
 * what stops the same name being re-examined from scratch every eighteen
 * months, and it is the artifact nobody ever has the discipline to write down
 * later. aktieblogg's 130-name rejection list is the same instinct.
 */

/** Five verbs, because a decision that needs a sixth is a note, not a call. */
const ACTIONS = [
  { id: "buy", label: "Buy", tone: "border-verdigris text-verdigris" },
  { id: "sell", label: "Sell", tone: "border-oxide text-oxide" },
  { id: "hold", label: "Hold", tone: "border-ink-line text-on-ink-soft" },
  { id: "watch", label: "Watch", tone: "border-cobalt text-cobalt" },
  { id: "pass", label: "Pass", tone: "border-cadmium text-cadmium" },
] as const;

export function CaptureView() {
  const { ticker: routeTicker } = useParams<{ ticker?: string }>();
  const { ticker: activeTicker } = useTicker();
  const qc = useQueryClient();

  const [ticker, setTicker] = useState(
    (routeTicker ?? activeTicker ?? "").toUpperCase(),
  );
  const [action, setAction] = useState<string | null>(null);
  const [rationale, setRationale] = useState("");
  const [conviction, setConviction] = useState<number | "">("");

  /* Shown under the form so a second thought lands beside the first rather
   * than replacing it, and so you can see you already passed on this name. */
  const prior = useQuery({
    queryKey: ["decisions", ticker],
    queryFn: () => api.getDecisions(ticker, 5),
    enabled: ticker.trim().length > 0,
    retry: false,
  });

  const save = useMutation({
    mutationFn: () =>
      api.recordDecision({
        ticker: ticker.trim().toUpperCase(),
        action: action ?? "watch",
        rationale: rationale.trim(),
        ...(conviction === "" ? {} : { conviction: Number(conviction) }),
      }),
    onSuccess: () => {
      setRationale("");
      setAction(null);
      setConviction("");
      qc.invalidateQueries({ queryKey: ["decisions"] });
    },
  });

  const ready = ticker.trim().length > 0 && action !== null;

  return (
    <div className="flex min-h-screen flex-col">
      <AppNav active="capture" />

      <div className="mx-auto flex w-full max-w-measure grow flex-col gap-lg p-md sm:p-lg">
        <div>
          <h1 className="font-display text-title-md tracking-tight text-bone">
            Capture
          </h1>
          <p className="mt-2xs text-body-sm text-on-ink-soft">
            A call and the reason for it, recorded now. The reason is the part
            that is worth anything later, and the part you will not reconstruct.
          </p>
        </div>

        <label className="flex flex-col gap-2xs">
          <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
            Company
          </span>
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="Ticker"
            autoCapitalize="characters"
            autoCorrect="off"
            spellCheck={false}
            className="border border-ink-line bg-ink px-sm py-sm font-display text-body text-bone outline-none transition-colors placeholder:text-on-ink-faint focus:border-cobalt"
          />
        </label>

        <div className="flex flex-col gap-2xs">
          <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
            Call
          </span>
          {/* Wraps rather than scrolls: a horizontally scrolling row of
            * choices hides options, and five is few enough to show at once. */}
          <div className="flex flex-wrap gap-xs">
            {ACTIONS.map((a) => {
              const on = action === a.id;
              return (
                <button
                  key={a.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setAction(on ? null : a.id)}
                  className={`grow basis-[30%] justify-center border px-sm py-sm font-display text-label uppercase tracking-label transition-colors ${
                    on ? `${a.tone} bg-ink-raised` : "border-ink-line text-on-ink-soft"
                  }`}
                >
                  {a.label}
                </button>
              );
            })}
          </div>
        </div>

        <label className="flex flex-col gap-2xs">
          <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
            Why
          </span>
          <textarea
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            rows={5}
            placeholder="What changed your mind, in your own words."
            className="resize-y border border-ink-line bg-ink px-sm py-sm text-body text-bone outline-none transition-colors placeholder:text-on-ink-faint focus:border-cobalt"
          />
        </label>

        <label className="flex flex-col gap-2xs">
          <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
            Conviction — optional, 0 to 100
          </span>
          <input
            value={conviction}
            onChange={(e) => {
              const v = e.target.value;
              if (v === "") return setConviction("");
              const n = Number(v);
              if (Number.isFinite(n) && n >= 0 && n <= 100) setConviction(n);
            }}
            inputMode="numeric"
            placeholder="—"
            className="tabular border border-ink-line bg-ink px-sm py-sm font-display text-body text-bone outline-none transition-colors placeholder:text-on-ink-faint focus:border-cobalt"
          />
        </label>

        <button
          type="button"
          disabled={!ready || save.isPending}
          onClick={() => save.mutate()}
          className="justify-center border border-cobalt bg-cobalt/10 px-md py-sm font-display text-label uppercase tracking-label text-bone transition-colors disabled:border-ink-line disabled:bg-transparent disabled:text-on-ink-faint"
        >
          {save.isPending ? "Recording…" : "Record"}
        </button>

        {save.isError && (
          <p className="text-body-sm text-oxide">
            Not recorded — {(save.error as Error).message}. Your machine may be
            asleep or off the network; nothing was lost, press Record again.
          </p>
        )}
        {save.isSuccess && (
          <p className="text-body-sm text-verdigris">Recorded.</p>
        )}

        {(prior.data?.decisions?.length ?? 0) > 0 && (
          <div className="flex flex-col gap-xs border-t border-ink-line pt-md">
            <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
              Already on {ticker}
            </p>
            <ul className="flex flex-col gap-xs">
              {prior.data?.decisions.slice(0, 5).map((d) => (
                <li key={d.id} className="border-b border-ink-line pb-xs last:border-b-0">
                  <p className="font-display text-label uppercase tracking-label text-on-ink-soft">
                    {d.action}
                    {d.conviction != null && (
                      <span className="tabular ml-xs text-on-ink-faint">
                        {d.conviction}
                      </span>
                    )}
                  </p>
                  {d.rationale && (
                    <p className="mt-2xs text-body-sm text-on-ink-soft">
                      {d.rationale}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
