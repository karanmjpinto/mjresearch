import {
  headlineField,
  isSigned,
  readField,
  unitFor,
  wordTone,
  type Reading,
  type Tone,
} from "@/lib/field-scales";
import { formatNumber, formatValue } from "@/lib/format";

/**
 * Reading a computed number.
 *
 * A plan node returns a dozen numbers of equal typographic weight, which is
 * exactly as informative as a list of digits: nothing tells you which one the
 * node is *about*, and nothing tells you whether 80.10 is a large number for
 * the thing being measured. These primitives fix both — one headline per node,
 * and every scaled value drawn against the domain it lives in.
 *
 * The drawing vocabulary is deliberately flat: square tracks, hairline ticks,
 * palette tokens only. A gradient or a rounded meter would read as chrome on a
 * surface whose whole argument is that the numbers are the ornament.
 */

const TONE_FILL: Record<Tone, string> = {
  up: "bg-verdigris",
  down: "bg-oxide",
  warn: "bg-cadmium",
  neutral: "bg-aluminium",
};

const TONE_TEXT: Record<Tone, string> = {
  up: "text-verdigris",
  down: "text-oxide",
  warn: "text-cadmium",
  neutral: "text-on-ink",
};

const TONE_BORDER: Record<Tone, string> = {
  up: "border-verdigris",
  down: "border-oxide",
  warn: "border-cadmium",
  neutral: "border-ink-line",
};

/**
 * The track: a value's position within its domain.
 *
 * Fills grow from the scale's origin, so a signed value reads as a departure
 * from zero rather than as a quantity. Multiples get a tick against a shaded
 * conventional band instead — the question there is "inside or outside the
 * usual range", not "how full".
 */
export function Track({ r, tall = false }: { r: Reading; tall?: boolean }) {
  const from = Math.min(r.origin, r.at);
  const to = Math.max(r.origin, r.at);
  const isTick = r.kind === "multiple";

  return (
    <div className={`relative w-full ${tall ? "h-2" : "h-1.5"} bg-ink-line`}>
      {r.band && (
        <div
          className="absolute inset-y-0 bg-on-ink-faint/30"
          style={{
            left: `${r.band[0] * 100}%`,
            width: `${(r.band[1] - r.band[0]) * 100}%`,
          }}
        />
      )}

      {isTick ? (
        <div
          className={`absolute -inset-y-0.5 w-0.5 ${TONE_FILL[r.tone]}`}
          style={{ left: `calc(${r.at * 100}% - 1px)` }}
        />
      ) : (
        <div
          className={`absolute inset-y-0 ${TONE_FILL[r.tone]}`}
          style={{
            left: `${from * 100}%`,
            width: `${Math.max((to - from) * 100, 1)}%`,
          }}
        />
      )}

      {/* Zero on a signed scale is a landmark, so it stays visible under the fill. */}
      {r.kind === "signed" && r.origin > 0.02 && r.origin < 0.98 && (
        <div
          className="absolute inset-y-0 w-px bg-ink"
          style={{ left: `${r.origin * 100}%` }}
        />
      )}

      {/* The value ran off the domain; the cap says so rather than lying flat. */}
      {r.clamped && (
        <div
          className={`absolute inset-y-0 w-1 bg-paper ${r.at > 0.5 ? "right-0" : "left-0"}`}
        />
      )}
    </div>
  );
}

/** The one number a node is about, sized so the eye lands on it first. */
export function HeadlineReading({
  name,
  value,
}: {
  name: string;
  value: number;
}) {
  const r = readField(name, value);
  if (!r) return null;

  return (
    <div className={`mt-sm border-l-2 pl-sm ${TONE_BORDER[r.tone]}`}>
      <div className="flex flex-wrap items-baseline gap-x-sm gap-y-2xs">
        <span
          className={`font-display text-display-sm tabular ${TONE_TEXT[r.tone]}`}
        >
          {formatNumber(value, { unit: r.unit, signed: r.kind === "signed" })}
        </span>
        <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
          {name}
        </span>
      </div>

      <div className="mt-xs max-w-md">
        <Track r={r} tall />
        <div className="mt-2xs flex items-baseline justify-between gap-sm font-display text-label text-on-ink-faint">
          <span>{r.ends[0]}</span>
          {r.bandLabel && (
            <span className="text-on-ink-soft">{r.bandLabel}</span>
          )}
          <span>{r.ends[1]}</span>
        </div>
      </div>
    </div>
  );
}

/**
 * A flag whose truth is the concern. `has_data_quality_concern: true` is not
 * neutral information, and colouring every boolean alike buries it.
 */
const CONCERN = /concern|error|warning|failed/;

function valueTone(name: string, value: unknown, r: Reading | null): string {
  if (r) return TONE_TEXT[r.tone];
  if (typeof value === "boolean") {
    if (!value) return "text-on-ink-faint";
    return CONCERN.test(name) ? TONE_TEXT.down : TONE_TEXT.neutral;
  }
  if (typeof value === "string") {
    const word = wordTone(value);
    if (word) return TONE_TEXT[word];
  }
  /* No scale, no reading: colour would be decoration, and in a view where
   * colour means something that is worse than plain. */
  return "text-on-ink";
}

/**
 * One field: name, value, and — where the field has a domain — the track it
 * sits on. Rows keep a single shape whether or not a track is drawn, so a
 * column of them still scans as a column.
 */
function FieldRow({ name, value }: { name: string; value: unknown }) {
  const r = typeof value === "number" ? readField(name, value) : null;
  const rendered =
    typeof value === "number"
      ? formatNumber(value, { unit: unitFor(name), signed: isSigned(name) })
      : formatValue(value);

  /* A list-valued field — `momentum, quality, valuation` — will not sit
   * opposite its own name in a grid column without shouldering the next cell
   * out of the way, so it stacks under the label instead. */
  if (typeof value === "string" && value.length > 16) {
    return (
      <div>
        <dt className="text-label text-on-ink-faint">{name}</dt>
        <dd className="mt-2xs break-words font-display text-label leading-snug text-on-ink">
          {rendered}
        </dd>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-baseline justify-between gap-sm">
        <dt className="min-w-0 break-words text-label text-on-ink-faint">
          {name}
        </dt>
        <dd
          className={`shrink-0 whitespace-nowrap font-display text-label tabular ${valueTone(
            name,
            value,
            r,
          )}`}
        >
          {rendered}
        </dd>
      </div>
      {r && (
        <div className="mt-2xs">
          <Track r={r} />
        </div>
      )}
    </div>
  );
}

/**
 * Where a price sat inside the window it was measured over.
 *
 * The four closes a price window returns describe a shape — a floor, a ceiling,
 * where it started and where it ended — and that shape is the answer to the
 * question people actually ask of a window. Four separate figures never show it.
 */
function RangeStrip({ values }: { values: Record<string, unknown> }) {
  const low = values.low as number;
  const high = values.high as number;
  const first = values.first_close as number;
  const last = values.last_close as number;
  const span = high - low;
  if (!(span > 0)) return null;

  const pos = (v: number) => ((v - low) / span) * 100;
  const rose = last >= first;

  return (
    <div className="mt-sm border-l-2 border-ink-line pl-sm">
      <div className="flex flex-wrap items-baseline gap-x-sm gap-y-2xs">
        <span
          className={`font-display text-display-sm tabular ${rose ? "text-verdigris" : "text-oxide"}`}
        >
          {formatValue(last)}
        </span>
        <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
          last close
        </span>
      </div>

      <div className="mt-xs max-w-md">
        <div className="relative h-2 bg-ink-line">
          {/* The travelled span, first close to last. */}
          <div
            className={`absolute inset-y-0 ${rose ? "bg-verdigris/40" : "bg-oxide/40"}`}
            style={{
              left: `${Math.min(pos(first), pos(last))}%`,
              width: `${Math.abs(pos(last) - pos(first))}%`,
            }}
          />
          <div
            className="absolute -inset-y-0.5 w-0.5 bg-aluminium"
            style={{ left: `calc(${pos(first)}% - 1px)` }}
          />
          <div
            className={`absolute -inset-y-1 w-0.5 ${rose ? "bg-verdigris" : "bg-oxide"}`}
            style={{ left: `calc(${pos(last)}% - 1px)` }}
          />
        </div>
        <div className="mt-2xs flex items-baseline justify-between font-display text-label text-on-ink-faint">
          <span>low {formatValue(low)}</span>
          <span className="text-on-ink-soft">opened {formatValue(first)}</span>
          <span>high {formatValue(high)}</span>
        </div>
      </div>
    </div>
  );
}

/** Risk flags arrive as one semicolon-joined string; they read as a list. */
function FlagList({ flags }: { flags: string }) {
  if (flags.trim().toLowerCase() === "none") {
    return (
      <p className="mt-sm border-l-2 border-verdigris pl-sm text-sm text-verdigris">
        No mechanical risk flags fired.
      </p>
    );
  }
  const items = flags
    .split(";")
    .map((f) => f.trim())
    .filter(Boolean);

  return (
    <ul className="mt-sm space-y-2xs">
      {items.map((f) => (
        <li
          key={f}
          className="border-l-2 border-oxide pl-sm text-sm leading-snug text-on-ink-soft"
        >
          {f}
        </li>
      ))}
    </ul>
  );
}

/**
 * A node's values: one headline, the composite shape where the fields describe
 * one, then the remainder as a scanned grid.
 */
export function NodeReadout({ values }: { values: Record<string, unknown> }) {
  const entries = Object.entries(values).filter(
    ([, v]) => v !== null && v !== undefined,
  );
  if (entries.length === 0) return null;

  const flags = typeof values.flags === "string" ? values.flags : null;

  /* A price window's four closes are one figure, not four, so the strip
   * replaces the headline rather than sitting beside it. */
  const isWindow = ["low", "high", "first_close", "last_close"].every(
    (k) => typeof values[k] === "number",
  );

  const headline = isWindow || flags ? null : headlineField(values);
  /* Whatever the headline or the strip already drew does not get repeated in
   * the grid — a figure shown twice reads as two figures. */
  const shown = new Set<string>(["flags", headline ?? ""]);
  if (isWindow)
    ["low", "high", "first_close", "last_close"].forEach((k) => shown.add(k));
  const rest = entries.filter(([k]) => !shown.has(k));

  return (
    <>
      {isWindow && <RangeStrip values={values} />}
      {flags && <FlagList flags={flags} />}
      {headline && (
        <HeadlineReading name={headline} value={values[headline] as number} />
      )}

      {rest.length > 0 && (
        <dl className="mt-sm grid gap-x-lg gap-y-sm sm:grid-cols-2 xl:grid-cols-3">
          {rest.map(([k, v]) => (
            <FieldRow key={k} name={k} value={v} />
          ))}
        </dl>
      )}
    </>
  );
}

/**
 * A count broken into its parts — 7 computed, 0 failed — drawn to width.
 * Two numbers in a header say what happened; the bar says it at a glance and
 * costs one line.
 */
export function SegmentBar({
  segments,
}: {
  segments: { label: string; count: number; tone: Tone }[];
}) {
  const total = segments.reduce((sum, s) => sum + s.count, 0);
  if (total === 0) return null;

  return (
    /* Hidden from assistive tech on purpose: every segment's count is already
     * in the heading text this bar sits beside, so announcing it again would
     * read the same figures twice. */
    <div
      className="flex h-1.5 w-32 overflow-hidden bg-ink-line"
      aria-hidden="true"
    >
      {segments
        .filter((s) => s.count > 0)
        .map((s) => (
          <div
            key={s.label}
            className={TONE_FILL[s.tone]}
            style={{ width: `${(s.count / total) * 100}%` }}
          />
        ))}
    </div>
  );
}

/**
 * A claim against the data behind it. Two bars to a shared scale is the whole
 * argument of the verifier: the prose said one length, the snapshot is another.
 */
export function ClaimCompare({
  stated,
  actual,
}: {
  stated: number;
  actual: number;
}) {
  const peak = Math.max(Math.abs(stated), Math.abs(actual)) || 1;
  const rows: { label: string; value: number; tone: Tone }[] = [
    /* The claim is the thing in question; the snapshot is the reference it is
     * being held against, so only one of the two bars is coloured as a fault. */
    { label: "claimed", value: stated, tone: "down" },
    { label: "computed", value: actual, tone: "neutral" },
  ];

  return (
    <div className="mt-xs max-w-sm space-y-2xs">
      {rows.map((row) => (
        <div key={row.label} className="flex items-center gap-sm">
          <span className="w-16 shrink-0 font-display text-label uppercase tracking-label text-on-ink-faint">
            {row.label}
          </span>
          <div className="h-1.5 flex-1 bg-ink-line">
            <div
              className={`h-full ${TONE_FILL[row.tone]}`}
              style={{
                width: `${Math.max((Math.abs(row.value) / peak) * 100, 1)}%`,
              }}
            />
          </div>
          <span className="w-16 shrink-0 text-right font-display text-label tabular text-on-ink">
            {formatValue(row.value)}
          </span>
        </div>
      ))}
    </div>
  );
}
