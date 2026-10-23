import { useQuery } from "@tanstack/react-query";
import { api, type BuySideItem, type BuySideWindow } from "@/lib/api";

/**
 * What the curated buy-side has written about one name (Bullpen.News).
 *
 * Titles, sources and links only. Bullpen's terms ask that their summaries are
 * not republished, and a title plus a link is also the honest unit: it is
 * somebody's argument, and the reader should go and read it rather than take
 * a one-line précis as the thesis. The summaries still reach the analysts'
 * prompt, labelled as opinion.
 */
export function BuySidePanel({ ticker }: { ticker: string }) {
  const q = useQuery({
    queryKey: ["commentary", ticker],
    queryFn: () => api.getCommentary(ticker),
    enabled: !!ticker,
    retry: false,
    staleTime: 30 * 60_000,
  });
  const d = q.data;

  if (q.isLoading) return <Note>Asking Bullpen.News…</Note>;
  if (q.isError || d?.unavailable)
    return (
      <Note>
        Bullpen.News could not be reached just now, so coverage is unknown —
        not zero. Try again in a minute.
      </Note>
    );
  if (!d?.covered)
    return (
      <Note>
        None of the ~400 curated sources Bullpen.News follows has written about{" "}
        {ticker}. For a contrarian that is a reading in itself: nobody serious
        is looking.
      </Note>
    );

  const windows = d.attention ? Object.values(d.attention) : [];
  const leads = d.catalyst_leads ?? [];
  // A lead is usually also recent; listing it twice reads as twice the coverage.
  const leadUrls = new Set(leads.map((l) => l.url));
  const recent = (d.recent ?? []).filter((it) => !leadUrls.has(it.url));
  const letters = d.letters;

  return (
    <section
      aria-label="Buy-side commentary"
      className="flex flex-col gap-md border border-ink-line bg-ink-raised p-md"
    >
      <dl className="grid grid-cols-2 gap-sm sm:grid-cols-4">
        {windows.map((w) => (
          <Stat key={w.days} label={`Last ${w.days} days`} {...countOf(w)} />
        ))}
        {letters && (
          <Stat
            label="Fund letters"
            value={`${letters.capped ? "≥" : ""}${letters.count}`}
            sub="mention it"
          />
        )}
      </dl>

      {leads.length > 0 && (
        <ItemList
          heading="Catalyst leads"
          hint="Tagged special situation, M&A or activism in the last six months. Someone's claim, not a verified catalyst — read it, then ask Bolton."
          items={leads}
        />
      )}

      <ItemList heading="Recent" items={recent} />

      {letters && letters.recent.length > 0 && (
        <div>
          <h3 className="font-display text-label uppercase tracking-label text-on-ink-faint">
            In fund letters
          </h3>
          <ul className="mt-2xs flex flex-col gap-2xs">
            {letters.recent.map((lt, i) => (
              <li key={`${lt.firm}-${i}`} className="text-body-sm text-on-ink-soft">
                <ExternalLink href={lt.url}>{lt.firm ?? "Unnamed firm"}</ExternalLink>
                {lt.period && (
                  <span className="text-on-ink-faint"> · {lt.period}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-body-xs text-on-ink-faint">
        Curated by{" "}
        <ExternalLink href="https://bullpen.news/">Bullpen.News</ExternalLink>.
        Opinions, not data: counts say how much serious attention the name gets,
        and a ≥ means Bullpen holds more history than was fetched.
      </p>
    </section>
  );
}

function countOf(w: BuySideWindow): { value: string; sub: string } {
  if (w.items == null) return { value: "—", sub: "not fetched" };
  const floor = w.complete ? "" : "≥";
  return {
    value: `${floor}${w.items}`,
    sub: `item${w.items === 1 ? "" : "s"} · ${w.sources ?? 0} source${w.sources === 1 ? "" : "s"}`,
  };
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div>
      <dt className="font-display text-label uppercase tracking-label text-on-ink-faint">
        {label}
      </dt>
      <dd className="mt-2xs font-display text-display-sm tabular text-bone">{value}</dd>
      <dd className="text-body-xs text-on-ink-soft">{sub}</dd>
    </div>
  );
}

function ItemList({
  heading,
  hint,
  items,
}: {
  heading: string;
  hint?: string;
  items: BuySideItem[];
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="font-display text-label uppercase tracking-label text-on-ink-faint">
        {heading}
      </h3>
      {hint && <p className="mt-2xs max-w-measure text-body-xs text-on-ink-soft">{hint}</p>}
      <ul className="mt-xs border-t border-ink-line">
        {items.map((it, i) => (
          <li key={`${it.url}-${i}`} className="border-b border-ink-line py-xs">
            <ExternalLink href={it.url}>{it.title}</ExternalLink>
            <p className="mt-2xs flex flex-wrap gap-x-xs text-body-xs text-on-ink-faint">
              <span>{it.source ?? "Unknown source"}</span>
              {it.published_at && <span className="tabular">{it.published_at.slice(0, 10)}</span>}
              {(it.catalyst ?? []).map((c) => (
                <span key={c} className="text-cadmium">
                  {c}
                </span>
              ))}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ExternalLink({ href, children }: { href: string | null; children: React.ReactNode }) {
  if (!href) return <span className="text-body-sm text-bone">{children}</span>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-body-sm text-cobalt underline-offset-2 transition-colors hover:text-cadmium hover:underline"
    >
      {children}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <p className="max-w-measure border border-ink-line bg-ink-raised p-md text-body-sm text-on-ink-soft">
      {children}
    </p>
  );
}
