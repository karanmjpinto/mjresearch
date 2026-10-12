import { Link } from "react-router-dom";
import { AppNav } from "./AppNav";
import { SectionCard } from "./SectionCard";
import { sectionByKey, type SectionKey } from "@/lib/sections";
import type { AppNavActive } from "./AppNav";

/**
 * The second level: one section, its doors, and a way back up.
 *
 * Find and Manage are the same screen with different contents, so they are
 * one component driven by `sections.ts` rather than two files that will
 * drift. Evaluate is not here because its entry is a text field, not a list
 * of doors, and pretending otherwise would put a fake door in front of the
 * only section that already has a well-designed path through it.
 */
export function SectionHub({
  section,
  active,
  children,
}: {
  section: SectionKey;
  active: AppNavActive;
  /** Optional content below the doors — a live count, a recent list. */
  children?: React.ReactNode;
}) {
  const s = sectionByKey(section);

  return (
    <div className="min-h-screen bg-ink">
      <AppNav active={active} />
      <main className="mx-auto max-w-4xl px-md py-xl sm:px-lg sm:py-2xl">
        <header className="mb-lg sm:mb-xl">
          {/* The way back is a link with a word, not a bare chevron. On the
            * second level of a four-level app the question "back to what?"
            * has a real answer and it costs four characters to give it. */}
          <Link
            to="/app"
            className="font-display text-label uppercase tracking-marker text-on-ink-faint transition-colors hover:text-bone"
          >
            ← All sections
          </Link>
          <div className="mt-sm flex items-baseline gap-sm">
            <span className="font-display text-label tabular tracking-marker text-cadmium">
              {s.num}
            </span>
            <h1 className="font-display text-display-md text-bone">
              {s.label}
            </h1>
          </div>
          <p className="mt-xs max-w-[60ch] text-sm leading-relaxed text-on-ink-soft">
            {s.question}
          </p>
        </header>

        <div className="flex flex-col gap-sm">
          {s.doors.map((d) => (
            <SectionCard
              key={d.to}
              to={d.to}
              label={d.label}
              blurb={d.blurb}
              status={d.status}
            />
          ))}
        </div>

        {children}
      </main>
    </div>
  );
}

export function FindView() {
  return <SectionHub section="find" active="find" />;
}

export function ManageView() {
  return <SectionHub section="manage" active="manage" />;
}
