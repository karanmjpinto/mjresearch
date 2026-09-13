import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AppNav } from "@/components/AppNav";
import {
  api,
  type ConstraintSummary,
  type LegView,
  type ValidationView,
} from "@/lib/api";
import { stagePath } from "@/lib/flow";

/**
 * The way in when you do not have a ticker yet.
 *
 * Own the strait, not the tanker: start from the scarce object, and the
 * companies fall out of it. The flow this feeds is unchanged — a name picked
 * here lands on stage 02 with the ticker filled in.
 *
 * The two columns are never merged. A curated constraint carrying dated
 * measurements from a filing and a subject lifted out of your own notes are
 * different kinds of claim, and interleaving them by score would make the
 * honest half wear the confident half's clothes. So they sit side by side,
 * labelled, and only one of them is ever scored.
 *
 * A constraint with no evidence reads as UNVALIDATED with its open questions,
 * not as a low score. The distinction is the point: a low score says "checked,
 * and it is weak", an unvalidated one says "nobody has checked" — and those
 * call for completely different next actions.
 */

const SYSTEM_LABEL: Record<string, string> = {
  intelligence: "Intelligence",
  power: "Power",
  motion: "Motion",
};

const LEG_ORDER = ["binding", "durability", "capture"] as const;

function Score({ value }: { value: number }) {
  const tone =
    value >= 0.5
      ? "text-cadmium"
      : value >= 0.2
        ? "text-on-ink"
        : "text-on-ink-soft";
  return (
    <span className={`font-display text-mark tabular ${tone}`}>
      {value.toFixed(2)}
    </span>
  );
}

function LegRow({ leg }: { leg: LegView }) {
  return (
    <li className="flex flex-col gap-2xs border-b border-ink-line py-xs last:border-b-0">
      <div className="flex items-baseline justify-between gap-md">
        <p className="text-body-sm text-bone">{leg.label}</p>
        {/* Compared inline rather than through a boolean so the null is
            actually narrowed away — a `const open = score === null` reads
            better and does not narrow. */}
        {leg.score === null ? (
          <span className="font-display text-label uppercase tracking-label text-cadmium">
            unanswered
          </span>
        ) : (
          <Score value={leg.score} />
        )}
      </div>
      {leg.open_questions.map((q) => (
        <p key={q} className="max-w-[72ch] text-body-xs text-on-ink-soft">
          {q}
        </p>
      ))}
    </li>
  );
}

function Validation({ v }: { v: ValidationView }) {
  const legs = [...(v.legs ?? [])].sort(
    (a, b) =>
      LEG_ORDER.indexOf(a.key as never) - LEG_ORDER.indexOf(b.key as never),
  );

  return (
    <div className="border border-ink-line bg-ink-raised p-md shadow-elev-1">
      <div className="flex flex-wrap items-baseline justify-between gap-md">
        <p className="font-display text-label uppercase tracking-label text-on-ink-soft">
          Does it hold up?
        </p>
        {v.available && v.score !== undefined ? (
          <p className="font-display text-label uppercase tracking-label text-bone">
            {v.label} · <Score value={v.score} />
          </p>
        ) : (
          <p className="font-display text-label uppercase tracking-label text-cadmium">
            unvalidated
          </p>
        )}
      </div>

      {v.available ? (
        <p className="mt-xs max-w-[72ch] text-body-sm text-on-ink-soft">
          Weakest link: <span className="text-bone">{v.weakest_leg}</span>. So{" "}
          <span className="text-cadmium">{v.structure?.allowed}</span> —{" "}
          {v.structure?.because}
        </p>
      ) : (
        <p className="mt-xs max-w-[72ch] text-body-sm text-on-ink-soft">
          {v.reason}
        </p>
      )}

      {legs.length > 0 && (
        <ul className="mt-sm">
          {legs.map((l) => (
            <LegRow key={l.key} leg={l} />
          ))}
        </ul>
      )}

      {/* Only shown when there are no legs to hang them off — otherwise each
          question already sits under the leg that is missing it. */}
      {legs.length === 0 && (
        <ul className="mt-sm flex flex-col gap-xs">
          {(v.open_questions ?? []).map((q) => (
            <li key={q} className="max-w-[72ch] text-body-xs text-on-ink-soft">
              {q}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Names({ id }: { id: string }) {
  const navigate = useNavigate();
  const q = useQuery({
    queryKey: ["constraint-candidates", id],
    queryFn: () => api.getConstraintCandidates(id),
  });

  if (q.isLoading) {
    return (
      <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
        Finding the names…
      </p>
    );
  }
  if (q.error || !q.data) return null;

  return (
    <div>
      <p className="font-display text-label uppercase tracking-label text-on-ink-faint">
        Ranked by {q.data.ranked_by}
      </p>
      <ul className="mt-xs">
        {q.data.names.map((n) => (
          <li
            key={n.ticker}
            className="border-b border-ink-line py-sm last:border-b-0"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-x-md gap-y-2xs">
              {/* Underlined on focus as well as recoloured. A colour swap
                  alone is not a focus indicator: it disappears for anyone who
                  cannot separate amber from bone, and this is the control that
                  actually leaves the page. */}
              <button
                type="button"
                onClick={() => navigate(stagePath("story", n.ticker))}
                aria-label={`Research ${n.ticker}, ${n.name}`}
                className="font-display text-mark text-cadmium underline-offset-4 transition-colors hover:text-bone hover:underline focus-visible:text-bone focus-visible:underline focus-visible:outline-none"
              >
                {n.ticker}
              </button>
              <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
                {n.band}
                {n.revenue_share_pct !== null &&
                n.revenue_share_pct !== undefined
                  ? ` · ${n.revenue_share_pct}% of revenue`
                  : ""}
              </span>
            </div>
            <p className="mt-2xs text-body-sm text-on-ink">{n.name}</p>
            <p className="mt-2xs max-w-[72ch] text-body-xs text-on-ink-soft">
              {n.exposure}
            </p>
            <p className="mt-2xs max-w-[72ch] text-body-xs text-on-ink-faint">
              {n.band_means}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CuratedCard({ c }: { c: ConstraintSummary }) {
  const [open, setOpen] = useState(false);

  return (
    <li className="border border-ink-line p-md">
      <div className="flex flex-wrap items-baseline justify-between gap-x-md gap-y-2xs">
        <h3 className="font-display text-title-xs text-bone">{c.name}</h3>
        <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
          {c.system ? SYSTEM_LABEL[c.system] : ""}
          {c.validation.available ? "" : " · unvalidated"}
        </span>
      </div>

      <p className="mt-2xs font-display text-label text-verdigris">
        {c.scarce_object}
      </p>
      <p className="mt-xs max-w-[72ch] text-body-sm text-on-ink-soft">
        {c.why}
      </p>

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="mt-sm border border-ink-line px-sm py-1.5 font-display text-label uppercase tracking-label text-bone transition-colors hover:border-cadmium hover:text-cadmium focus-visible:border-cadmium focus-visible:outline-none"
      >
        {open ? "Hide the working" : `The working & ${c.name_count} names`}
      </button>

      {open && (
        <div className="mt-md flex flex-col gap-md border-t border-ink-line pt-md">
          <Validation v={c.validation} />
          <Names id={c.id} />
        </div>
      )}
    </li>
  );
}

function DerivedCard({ c }: { c: ConstraintSummary }) {
  const [open, setOpen] = useState(false);
  const quotes = c.evidence_in_your_words ?? [];

  return (
    <li className="border border-dashed border-ink-line p-md">
      <div className="flex flex-wrap items-baseline justify-between gap-x-md gap-y-2xs">
        <h3 className="font-display text-title-xs capitalize text-bone">
          {c.name}
        </h3>
        <span className="font-display text-label uppercase tracking-label text-on-ink-faint">
          {c.flagged_count}/{c.note_count} notes
        </span>
      </div>
      <p className="mt-xs max-w-[72ch] text-body-sm text-on-ink-soft">
        {c.why}
      </p>

      {quotes.length > 0 && (
        <blockquote className="mt-sm border-l-2 border-verdigris pl-sm">
          <p className="max-w-[72ch] text-body-xs italic text-on-ink-soft">
            {quotes[0].quote}
          </p>
          <cite className="mt-2xs block font-display text-label not-italic text-on-ink-faint">
            {quotes[0].title} · “{quotes[0].term}”
          </cite>
        </blockquote>
      )}

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="mt-sm border border-ink-line px-sm py-1.5 font-display text-label uppercase tracking-label text-bone transition-colors hover:border-cadmium hover:text-cadmium focus-visible:border-cadmium focus-visible:outline-none"
      >
        {open ? "Hide" : "What would make this investable"}
      </button>

      {open && (
        <div className="mt-md border-t border-ink-line pt-md">
          <Validation v={c.validation} />
        </div>
      )}
    </li>
  );
}

export function ConstraintsView() {
  const [system, setSystem] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["constraints", system],
    queryFn: () => api.getConstraints(system),
  });

  const d = q.data;

  // Read every group defensively. The type says these are always present, but
  // a type describes what the server should send rather than what it did: a
  // frontend deployed either side of a backend change will meet a response
  // missing a group, and reaching straight into it took down the whole page
  // rather than hiding one section.
  const curated = d?.curated?.constraints ?? [];
  const mine = d?.from_your_notes?.constraints ?? [];
  const dismissed = d?.checked_and_rejected?.constraints ?? [];

  return (
    <div className="flex min-h-dvh flex-col bg-ink">
      <AppNav active="screeners" />

      <main className="mx-auto w-full max-w-6xl px-lg py-2xl">
        <p className="font-display text-label uppercase tracking-marker text-on-ink-faint">
          No ticker yet
        </p>
        <h1 className="mt-xs font-display text-display-sm text-bone">
          Start from the constraint
        </h1>
        <p className="mt-sm max-w-[64ch] text-body-lg text-on-ink-soft">
          Find what the boom cannot scale without, check that it actually holds,
          then take the names it points at into the normal flow.
        </p>

        <div
          className="mt-lg flex flex-wrap gap-xs"
          role="group"
          aria-label="Filter by system"
        >
          {[null, ...(d?.systems ?? [])].map((s) => (
            <button
              key={s ?? "all"}
              type="button"
              onClick={() => setSystem(s)}
              aria-pressed={system === s}
              className={`border px-sm py-1.5 font-display text-label uppercase tracking-label transition-colors ${
                system === s
                  ? "border-cadmium text-cadmium"
                  : "border-ink-line text-on-ink-soft hover:border-on-ink-faint hover:text-bone"
              }`}
            >
              {s === null ? "All" : SYSTEM_LABEL[s]}
            </button>
          ))}
        </div>

        {q.isLoading && (
          <p className="mt-xl font-display text-label uppercase tracking-label text-on-ink-faint">
            Reading the map…
          </p>
        )}

        {q.error && (
          <div className="mt-xl border border-oxide bg-ink-raised p-md">
            <p className="font-display text-label uppercase tracking-label text-cadmium">
              Could not load the constraint map
            </p>
            <p className="mt-xs max-w-[68ch] text-body-sm text-on-ink-soft">
              {q.error instanceof Error ? q.error.message : "unknown error"}
            </p>
            <button
              type="button"
              onClick={() => void q.refetch()}
              disabled={q.isFetching}
              className="mt-sm border border-ink-line px-sm py-1.5 font-display text-label uppercase tracking-label text-bone transition-colors hover:border-cadmium hover:text-cadmium focus-visible:border-cadmium focus-visible:outline-none disabled:opacity-50"
            >
              {q.isFetching ? "Retrying…" : "Try again"}
            </button>
          </div>
        )}

        {d && (
          <div className="mt-xl grid gap-2xl lg:grid-cols-2">
            <section aria-label="Researched constraints">
              <div className="border-b border-ink-line pb-xs">
                <h2 className="font-display text-label uppercase tracking-label text-cadmium">
                  Researched
                  <span className="ml-xs text-on-ink-faint">
                    {curated.length}
                  </span>
                </h2>
                <p className="mt-2xs max-w-[52ch] text-body-xs text-on-ink-faint">
                  Dated measurements with a source. Scored, and only when the
                  evidence is there.
                </p>
              </div>
              {d.curated?.note && (
                <p className="py-sm text-body-sm text-on-ink-soft">
                  {d.curated?.note}
                </p>
              )}
              <ul className="mt-sm flex flex-col gap-md">
                {curated.map((c) => (
                  <CuratedCard key={c.id} c={c} />
                ))}
              </ul>
            </section>

            <section aria-label="Constraints from your own notes">
              <div className="border-b border-ink-line pb-xs">
                <h2 className="font-display text-label uppercase tracking-label text-verdigris">
                  From your notes
                  <span className="ml-xs text-on-ink-faint">{mine.length}</span>
                </h2>
                <p className="mt-2xs max-w-[52ch] text-body-xs text-on-ink-faint">
                  Subjects you already write about as constraints. Never scored
                  — a note is not a measurement.
                </p>
              </div>
              {d.from_your_notes?.note && (
                <p className="py-sm max-w-[52ch] text-body-sm text-on-ink-soft">
                  {d.from_your_notes?.note}
                </p>
              )}
              <ul className="mt-sm flex flex-col gap-md">
                {mine.map((c) => (
                  <DerivedCard key={c.id} c={c} />
                ))}
              </ul>
            </section>
          </div>
        )}

        {dismissed.length > 0 && (
          <section
            className="mt-2xl border-t border-ink-line pt-lg"
            aria-label="Checked and rejected"
          >
            {/* Collapsed by default. A negative result is worth keeping and not
                worth leading with — its job is to stop you re-researching the
                same idea, which it does from behind one click. */}
            <details>
              <summary className="cursor-pointer font-display text-label uppercase tracking-label text-on-ink-soft transition-colors hover:text-bone">
                Checked and rejected
                <span className="ml-xs text-on-ink-faint">
                  {dismissed.length}
                </span>
              </summary>
              <p className="mt-xs max-w-[72ch] text-body-xs text-on-ink-faint">
                {d?.checked_and_rejected?.note}
              </p>
              <ul className="mt-sm flex flex-col gap-sm">
                {dismissed.map((c) => (
                  <li key={c.id} className="border-l-2 border-ink-line pl-md">
                    <h3 className="font-display text-body-sm text-on-ink">
                      {c.name}
                    </h3>
                    <p className="mt-2xs max-w-[72ch] text-body-xs text-on-ink-soft">
                      {c.rejected_because}
                    </p>
                  </li>
                ))}
              </ul>
            </details>
          </section>
        )}
      </main>
    </div>
  );
}
