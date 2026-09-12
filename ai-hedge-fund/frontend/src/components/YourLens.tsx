import { useQuery } from "@tanstack/react-query";
import { api, type LensMatch, type LensView } from "@/lib/api";

/**
 * Stage 04 — what you have already written about this name.
 *
 * Every row states the rule that surfaced it. A list of "related notes" with
 * no reason is unfalsifiable: you cannot tell a real connection from two words
 * colliding, and the only thing this stage is for is knowing whether your own
 * thinking already covers a name.
 *
 * The three kinds are deliberately unequal and shown as such. A company note
 * is coverage. A theme note is context. A framework is a lens — it applies to
 * every company, so it is never counted as knowledge of this one. Collapsing
 * that distinction is what would let a vault full of general models look like
 * deep knowledge of the whole market.
 *
 * Thin coverage is printed as a finding rather than hidden. "Nothing here is
 * yours yet" is the single most useful thing this panel can say, because it
 * tells you the edge has to come from somewhere else.
 */

const KIND_COLOR: Record<string, string> = {
  company: "text-cadmium",
  themes: "text-verdigris",
  frameworks: "text-cobalt",
};

function MatchRow({ match, accent }: { match: LensMatch; accent: string }) {
  return (
    <li className="border-b border-ink-line py-sm last:border-b-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-md gap-y-2xs">
        <p className="text-body-sm text-bone">{match.title}</p>
        <p className={`font-display text-label ${accent}`}>{match.reason}</p>
      </div>
      {match.tags.length > 0 && (
        <p className="mt-2xs font-display text-label text-on-ink-faint">
          {match.tags
            .slice(0, 6)
            .map((t) => `#${t}`)
            .join("  ")}
        </p>
      )}
    </li>
  );
}

function Group({
  kind,
  heading,
  note,
  rows,
  hidden,
}: {
  kind: keyof typeof KIND_COLOR;
  heading: string;
  note: string;
  rows: LensMatch[];
  hidden: number;
}) {
  const accent = KIND_COLOR[kind];
  return (
    <section aria-label={heading}>
      <div className="flex items-baseline justify-between gap-md border-b border-ink-line pb-xs">
        <h3
          className={`font-display text-label uppercase tracking-label ${accent}`}
        >
          {heading}
          <span className="ml-xs text-on-ink-faint">{rows.length}</span>
        </h3>
        <p className="max-w-[42ch] text-right text-body-xs text-on-ink-faint">
          {note}
        </p>
      </div>

      {rows.length === 0 ? (
        <p className="py-sm text-body-sm text-on-ink-faint">None.</p>
      ) : (
        <ul>
          {rows.map((m) => (
            <MatchRow key={`${m.kind}:${m.path}`} match={m} accent={accent} />
          ))}
        </ul>
      )}

      {hidden > 0 && (
        <p className="pt-xs text-body-xs text-on-ink-faint">
          {hidden} more not shown — open the vault to read the rest.
        </p>
      )}
    </section>
  );
}

function CoverageBar({ data }: { data: LensView }) {
  const { score, label, company_notes, theme_notes } = data.coverage;
  // The bar is the same colour the label implies, so the number and the word
  // never disagree: amber for direct coverage, teal for context only.
  const tone =
    label === "direct"
      ? "bg-cadmium"
      : label === "thematic"
        ? "bg-verdigris"
        : "bg-oxide";

  return (
    <div className="border border-ink-line bg-ink-raised p-md">
      <div className="flex flex-wrap items-end justify-between gap-md">
        <div>
          <p className="font-display text-label uppercase tracking-label text-on-ink-soft">
            Coverage in your own notes
          </p>
          <p className="mt-2xs font-display text-display-sm capitalize text-bone">
            {label}
          </p>
        </div>
        <p className="font-display text-mark text-bone tabular">
          {score.toFixed(2)}
        </p>
      </div>

      <div className="mt-sm h-1 rounded bg-ink" aria-hidden>
        <div
          className={`h-full rounded ${tone}`}
          style={{ width: `${Math.max(score * 100, 1)}%` }}
        />
      </div>

      <p className="mt-sm max-w-[68ch] text-body-sm text-on-ink-soft">
        {data.finding}
      </p>
      <p className="mt-xs font-display text-label text-on-ink-faint">
        {company_notes} on the company · {theme_notes} on the themes around it
        {data.vault ? ` · ${data.vault.notes} notes indexed` : ""}
      </p>
    </div>
  );
}

export function YourLens({ ticker }: { ticker: string }) {
  const q = useQuery({
    queryKey: ["lens", ticker],
    queryFn: () => api.getLens(ticker),
    enabled: Boolean(ticker),
  });

  if (q.isLoading) {
    return (
      <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
        Reading your notes…
      </p>
    );
  }

  if (q.error || !q.data) {
    return (
      <div className="border border-oxide bg-ink-raised p-md">
        <p className="font-display text-label uppercase tracking-label text-cadmium">
          Could not read your notes
        </p>
        <p className="mt-xs max-w-[68ch] text-body-sm text-on-ink-soft">
          {q.error instanceof Error ? q.error.message : "unknown error"}
        </p>
        {/* A dead end is not an answer. Reading the vault is a local file walk,
            so the usual cause is transient — a drive waking up, a permission
            granted a moment ago — and retrying is genuinely worth offering. */}
        <button
          type="button"
          onClick={() => void q.refetch()}
          disabled={q.isFetching}
          className="mt-sm border border-ink-line px-sm py-1.5 font-display text-label uppercase tracking-label text-bone transition-colors hover:border-cadmium hover:text-cadmium focus-visible:border-cadmium focus-visible:outline-none disabled:opacity-50"
        >
          {q.isFetching ? "Retrying…" : "Try again"}
        </button>
      </div>
    );
  }

  const d = q.data;

  // Two non-answers, kept apart because the fix is different: there is no
  // vault, or there is one and it did not respond. Collapsing them into one
  // "unavailable" message would send you looking for the wrong problem.
  if (d.unreadable) {
    return (
      <div className="border border-dashed border-oxide bg-ink-raised p-md">
        {/* Amber, not oxide. Oxide text on this ground measures 2.76:1, below
            even the 3.0 floor for UI text — the border carries the alarm
            instead, where contrast is not load-bearing for reading. */}
        <p className="font-display text-label uppercase tracking-label text-cadmium">
          Notes folder did not respond
        </p>
        <p className="mt-xs max-w-[68ch] text-body-sm text-on-ink-soft">
          {d.finding}
        </p>
      </div>
    );
  }

  // Not an error state. No vault is a configuration this stage supports, and
  // saying so plainly beats an empty panel that looks like a failed request.
  if (!d.configured) {
    return (
      <div className="border border-dashed border-ink-line bg-ink-raised p-md">
        <p className="font-display text-label uppercase tracking-label text-cadmium">
          No vault connected
        </p>
        <p className="mt-xs max-w-[68ch] text-body-sm text-on-ink-soft">
          {d.finding}
        </p>
        <p className="mt-sm max-w-[68ch] text-body-xs text-on-ink-faint">
          Nothing is uploaded and the path is never committed — the notes are
          read from disk on this machine only.
        </p>
      </div>
    );
  }

  return (
    <section
      className="flex flex-col gap-lg"
      aria-label={`Your notes on ${ticker}`}
    >
      <CoverageBar data={d} />

      {d.subject?.sector && (
        <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
          Matched as {d.subject.name ?? ticker} · {d.subject.sector}
          {d.subject.industry ? ` · ${d.subject.industry}` : ""}
        </p>
      )}

      <Group
        kind="company"
        heading="On this company"
        note="Direct coverage — the ticker or the name appears."
        rows={d.company}
        hidden={d.truncated?.company ?? 0}
      />
      <Group
        kind="themes"
        heading="On the themes around it"
        note="Context. A shared subject, not a shared word."
        rows={d.themes}
        hidden={d.truncated?.themes ?? 0}
      />
      <Group
        kind="frameworks"
        heading="Lenses you can point at it"
        note="These apply to any company, so they are never counted as coverage of this one."
        rows={d.frameworks}
        hidden={d.truncated?.frameworks ?? 0}
      />
    </section>
  );
}
