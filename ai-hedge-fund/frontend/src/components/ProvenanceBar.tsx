import { useMemo, useState } from "react";
import { TRUST_META, type Trust } from "@/content/docs";

/**
 * How much of this is a fact, and how much is an opinion.
 *
 * The app's whole argument is that a reader can tell a calculated figure from
 * a predicted one, and until now that argument was made one label at a time:
 * every capability in the reference carries a `trust` value, and nobody could
 * see the shape of the whole. A desk that is 78% computed and one that is 31%
 * computed make very different claims, and both looked identical.
 *
 * So this is the aggregate, as one bar. It is deliberately the first thing on
 * anything it appears above, not a footnote — a provenance summary printed
 * underneath the conclusions is a disclaimer, and a disclaimer is what you
 * write when you would rather the reader did not notice.
 *
 * ORDINAL, NOT CATEGORICAL, and the segments are therefore ordered by
 * distance from fact rather than by size. Sorting by size would put the
 * biggest slice first and destroy the reading the bar exists for: left is
 * what you can re-derive, right is what you cannot, and the eye should travel
 * that way. See `--c-prov-*` in index.css for why the colours are a lightness
 * ramp rather than four hues.
 */
export type ProvenanceCounts = Record<Trust, number>;

/** The scale, in order. Not alphabetical, not by frequency — by certainty. */
export const TRUST_ORDER: readonly Trust[] = [
  "computed",
  "chosen-then-computed",
  "written",
  "judged",
] as const;

const TOKEN: Record<Trust, string> = {
  computed: "var(--prov-computed)",
  "chosen-then-computed": "var(--prov-chosen)",
  written: "var(--prov-written)",
  judged: "var(--prov-judged)",
};

export function countTrust(items: readonly { trust: Trust }[]): ProvenanceCounts {
  const out: ProvenanceCounts = {
    computed: 0,
    "chosen-then-computed": 0,
    written: 0,
    judged: 0,
  };
  for (const i of items) out[i.trust] += 1;
  return out;
}

export function ProvenanceBar({
  counts,
  title = "What this is made of",
  caption,
  compact = false,
}: {
  counts: ProvenanceCounts;
  title?: string;
  /** One line naming what was counted, so a percentage is not free-floating. */
  caption?: string;
  /** Bar and one summary line only — for a report header. */
  compact?: boolean;
}) {
  const [showTable, setShowTable] = useState(false);

  const { total, rows } = useMemo(() => {
    const t = TRUST_ORDER.reduce((n, k) => n + counts[k], 0);
    return {
      total: t,
      rows: TRUST_ORDER.map((k) => ({
        key: k,
        n: counts[k],
        pct: t > 0 ? (counts[k] / t) * 100 : 0,
        meta: TRUST_META[k],
      })),
    };
  }, [counts]);

  if (total === 0) return null;

  const computedPct = Math.round((counts.computed / total) * 100);

  return (
    <figure className="m-0">
      <figcaption className="mb-xs flex flex-wrap items-baseline justify-between gap-x-sm gap-y-2xs">
        <span className="font-display text-label uppercase tracking-marker text-on-ground-faint">
          {title}
        </span>
        {/* The headline the bar exists to deliver, in words, because a reader
            who only reads one thing should read this one. */}
        <span className="text-sm text-on-ground-soft">
          <strong className="tabular font-semibold text-on-ground">
            {computedPct}%
          </strong>{" "}
          computed
          <span className="text-on-ground-faint"> · {total} items</span>
        </span>
      </figcaption>

      {/* 2px gaps between segments, so two adjacent fills never share an edge.
          The ramp is monotonic in lightness, but a seam is what makes the
          boundary readable when two steps are close. */}
      <div
        className="flex h-3 w-full gap-[2px] overflow-hidden"
        role="img"
        aria-label={rows
          .filter((r) => r.n > 0)
          .map((r) => `${r.meta.label}: ${r.n} of ${total}`)
          .join("; ")}
      >
        {rows
          .filter((r) => r.n > 0)
          .map((r) => (
            <div
              key={r.key}
              style={{ width: `${r.pct}%`, background: TOKEN[r.key] }}
              title={`${r.meta.label} — ${r.n} of ${total} (${Math.round(r.pct)}%)`}
            />
          ))}
      </div>

      {!compact && (
        <>
          {/* Always a legend, never colour alone: four steps of one ramp are
              distinguishable, and a reader should not have to rely on that. */}
          <ul className="mt-sm grid gap-x-md gap-y-2xs sm:grid-cols-2">
            {rows.map((r) => (
              <li key={r.key} className="flex items-baseline gap-xs">
                <span
                  aria-hidden="true"
                  className="mt-[3px] inline-block h-2 w-2 shrink-0"
                  style={{ background: TOKEN[r.key] }}
                />
                <span className="text-sm text-on-ground-soft">
                  <span className="text-on-ground">{r.meta.label}</span>
                  <span className="tabular text-on-ground-faint">
                    {" "}
                    {r.n} · {Math.round(r.pct)}%
                  </span>
                </span>
              </li>
            ))}
          </ul>

          {caption && (
            <p className="mt-xs text-sm text-on-ground-faint">{caption}</p>
          )}

          <button
            type="button"
            onClick={() => setShowTable((v) => !v)}
            aria-expanded={showTable}
            className="mt-xs font-display text-label uppercase tracking-marker text-on-ground-faint underline underline-offset-2 transition-colors hover:text-on-ground"
          >
            {showTable ? "Hide the numbers" : "Read it as a table"}
          </button>

          {/* The table is not a courtesy. A proportion encoded only as width
              is unreadable to anyone the bar fails — print, forced colours,
              a screen reader reading left to right — and this is the figure
              the page is arguing with. */}
          {showTable && (
            <div className="mt-xs overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr>
                    {["Kind", "Count", "Share", "What it means"].map((h) => (
                      <th
                        key={h}
                        scope="col"
                        className="border-b border-border px-0 py-2xs pr-md text-left font-display text-label uppercase tracking-marker text-on-ground-faint"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.key}>
                      <td className="border-b border-border py-2xs pr-md text-on-ground">
                        {r.meta.label}
                      </td>
                      <td className="tabular border-b border-border py-2xs pr-md text-on-ground">
                        {r.n}
                      </td>
                      <td className="tabular border-b border-border py-2xs pr-md text-on-ground">
                        {Math.round(r.pct)}%
                      </td>
                      <td className="border-b border-border py-2xs text-on-ground-soft">
                        {r.meta.meaning}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </figure>
  );
}
