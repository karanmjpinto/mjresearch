import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

/** Below this many scored calls, your own rate is noise; show the professional base rate. */
const OWN_RATE_MIN_CALLS = 30;

interface Props {
  score: number | null;
  label?: string;
}

export function ConvictionGauge({ score, label }: Props) {
  const displayScore = score ?? 0;
  const isActive = score !== null;
  const cal = useQuery({
    queryKey: ["decision-calibration"],
    queryFn: api.getDecisionCalibration,
    staleTime: 5 * 60_000,
  });
  const own = cal.data && cal.data.n >= OWN_RATE_MIN_CALLS ? cal.data : null;

  // Score band -> palette token. Tokens, not hex, so the gauge tracks the
  // palette in index.css instead of drifting from it.
  const getColor = (s: number) => {
    if (s >= 75) return "var(--verdigris)";
    if (s >= 50) return "var(--cadmium)";
    return "var(--oxide)";
  };

  const getLabel = (s: number) => {
    if (s >= 75) return "BUY";
    if (s >= 50) return "HOLD";
    return "SELL";
  };

  const circumference = 2 * Math.PI * 45;
  const offset = circumference - (displayScore / 100) * circumference * 0.75; // 270deg arc

  return (
    <div className="bg-surface-card rounded-xl p-4 flex flex-col items-center gap-2">
      <p className="text-label uppercase tracking-[0.14em] text-on-ink-soft">
        Conviction Score
      </p>

      <div className="relative w-32 h-32">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-[135deg]">
          {/* Background arc */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke="var(--ink-line)"
            strokeWidth="8"
            strokeDasharray={`${circumference * 0.75} ${circumference}`}
            strokeLinecap="round"
          />
          {/* Score arc */}
          {isActive && (
            <circle
              cx="50"
              cy="50"
              r="45"
              fill="none"
              stroke={getColor(displayScore)}
              strokeWidth="8"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              strokeLinecap="round"
              className="transition-all duration-1000 ease-out"
            />
          )}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold text-white font-mono">
            {isActive ? displayScore : "—"}
          </span>
          <span
            className="text-xs font-semibold"
            style={{
              color: isActive ? getColor(displayScore) : "var(--on-ink-faint)",
            }}
          >
            {isActive ? getLabel(displayScore) : (label ?? "N/A")}
          </span>
        </div>
      </div>

      {isActive && (
        /* Dimensional's question: are those odds you would bet your savings on?
         * A high score is a claim to beat the index, so show how often that claim
         * comes true — the professionals' rate until your own record is large enough. */
        <p className="text-center text-label leading-relaxed text-on-ink-faint">
          {own
            ? `Your calls beat the index ${own.hit_rate_pct}% of the time (${own.n} calls).`
            : "About 1 US equity fund in 8 survived and beat its index, 2006–2025."}
        </p>
      )}

      {!isActive && (
        /* This used to read "Enable 'Run AI thesis'", which was a button on
         * this screen. There is no button now — the analysis runs on its own
         * at stage 03 — so the empty state points at where the score comes
         * from rather than at a control that no longer exists. */
        <p className="text-center text-label leading-relaxed text-on-ink-faint">
          Scored at stage 03, Analysis. Needs a local model running.
        </p>
      )}
    </div>
  );
}
