/**
 * Value formatting shared by every view that prints a computed number.
 *
 * Kept out of the components so the plan view, the readout primitives and
 * anything added later round and abbreviate identically — a number that reads
 * `6.92B` in one place and `6920000000` in another is the same bug as a wrong
 * number, just quieter.
 */

/** A bare value as it should appear in a cell: rounded, abbreviated, never `null`. */
export function formatValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "—";
    if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
    if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
    return Number.isInteger(v) ? String(v) : v.toFixed(2);
  }
  return String(v);
}

/**
 * A number carrying its unit, and its sign when the sign is the point.
 *
 * Returns are shown as `+48.28%` rather than `48.28` because the leading glyph
 * is what the eye reads first — losing it costs a reader the one fact they
 * needed before parsing any digits.
 */
export function formatNumber(
  v: number,
  { unit, signed = false }: { unit?: string; signed?: boolean } = {}
): string {
  const body = formatValue(v);
  const sign = signed && v > 0 ? "+" : "";
  return `${sign}${body}${unit ?? ""}`;
}
