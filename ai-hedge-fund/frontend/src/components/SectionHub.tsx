import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AppNav } from "./AppNav";
import { SectionCard } from "./SectionCard";
import { sectionByKey, type SectionKey } from "@/lib/sections";
import { OutlierMap } from "./OutlierMap";
import { api } from "@/lib/api";
import { DEFAULT_SCREENER_ID, getScreenerById } from "@/config/screeners";
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

/**
 * Find carries the map as well as the two doors.
 *
 * The doors are the two ways in; the map is what you came for. It reads the
 * most recent cached run of the default screen with `passingOnly` off, because
 * a plot of only the names that passed is a plot with its own answer already
 * applied — the distribution is the information, and a name sitting just
 * outside the filters is exactly the one worth arguing about.
 */
export function FindView() {
  /* `id` and `screenId` are not the same string and the difference is silent:
   * the routes spell this screen `acquisition_compounder` and the API spells
   * it `acquisition-compounder`. Passing the route id returns a 404 that
   * renders as "no cached run", which reads as a desk that has never run
   * anything rather than as a mistyped path. */
  const screenId = getScreenerById(DEFAULT_SCREENER_ID)?.screenId;
  const results = useQuery({
    queryKey: ["screen-results", screenId, "map"],
    queryFn: () =>
      api.getScreenResults(screenId as string, { limit: 500, passingOnly: false }),
    enabled: Boolean(screenId),
    retry: false,
  });

  const data = results.data;
  const rows = data && data.available ? data.results : [];

  return (
    <SectionHub section="find" active="find">
      <section aria-labelledby="map-heading" className="mt-2xl">
        <h2
          id="map-heading"
          className="font-display text-label uppercase tracking-marker text-on-ink-faint"
        >
          The field
        </h2>
        <p className="mt-2xs max-w-[60ch] text-sm text-on-ink-soft">
          Every name in the last run of the quality screen, not just the ones
          that passed. A ranked table tells you what scored highest; this tells
          you whether the top name is genuinely apart from the field.
        </p>

        <div className="mt-md">
          {results.isLoading && (
            <p className="text-sm text-on-ink-faint">Reading the last run…</p>
          )}
          {results.isError && (
            <p className="text-sm text-on-ink-faint">
              Could not read the cached screens. The map needs a run to plot.
            </p>
          )}
          {data && !data.available && (
            <p className="text-sm text-on-ink-faint">
              No cached run to plot yet. Build one with{" "}
              <code className="text-on-ink-soft">{data.refresh_command}</code>.
            </p>
          )}
          {rows.length > 0 && (
            <OutlierMap
              rows={rows}
              caption={
                data && data.available
                  ? `From the ${data.screen} run over ${data.universe}, built ${new Date(data.built_at).toLocaleDateString()}${data.stale ? " — stale" : ""}.`
                  : undefined
              }
            />
          )}
        </div>
      </section>
    </SectionHub>
  );
}

export function ManageView() {
  return <SectionHub section="manage" active="manage" />;
}
