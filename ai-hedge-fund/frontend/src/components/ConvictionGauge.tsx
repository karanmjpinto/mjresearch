interface Props {
  score: number | null;
  label?: string;
}

export function ConvictionGauge({ score, label }: Props) {
  const displayScore = score ?? 0;
  const isActive = score !== null;

  // Color based on score
  const getColor = (s: number) => {
    if (s >= 75) return "#10B981"; // green
    if (s >= 50) return "#F59E0B"; // yellow
    return "#EF4444"; // red
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
      <p className="text-xs text-gray-500 uppercase tracking-wider">Conviction Score</p>

      <div className="relative w-32 h-32">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-[135deg]">
          {/* Background arc */}
          <circle
            cx="50" cy="50" r="45"
            fill="none"
            stroke="#1E2736"
            strokeWidth="8"
            strokeDasharray={`${circumference * 0.75} ${circumference}`}
            strokeLinecap="round"
          />
          {/* Score arc */}
          {isActive && (
            <circle
              cx="50" cy="50" r="45"
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
            style={{ color: isActive ? getColor(displayScore) : "#6B7280" }}
          >
            {isActive ? getLabel(displayScore) : (label ?? "N/A")}
          </span>
        </div>
      </div>

      {!isActive && (
        <p className="text-xs text-gray-600 text-center">
          Enable &quot;Run AI thesis&quot; — needs Ollama running with your model pulled
        </p>
      )}
    </div>
  );
}
