import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import clsx from "clsx";

import {
  GAPS,
  OPENING,
  SECTIONS,
  TRUST_META,
  type Trust,
} from "@/content/docs";

/**
 * The reference section.
 *
 * Sits outside the backend gate, with the landing page, because documentation
 * is the one thing you want to be able to read *without* running anything —
 * including from the published static build, where there is no API at all.
 *
 * Laid out as a document rather than a dashboard: one column at a readable
 * measure, a contents rail that tracks position, and no cards. The subject is
 * prose and the page should look like prose. The one piece of visual
 * machinery is the trust chip, because "was this calculated or predicted" is
 * the question the whole document exists to answer and it should be readable
 * at a glance rather than inferred from a paragraph.
 */

function TrustChip({ trust }: { trust: Trust }) {
  const m = TRUST_META[trust];
  return (
    <span
      className="inline-flex shrink-0 items-center gap-2xs border px-xs py-[2px] font-display text-label uppercase tracking-label"
      style={{ borderColor: m.hue, color: m.hue }}
      title={m.meaning}
    >
      {m.label}
    </span>
  );
}

/** Contents, and which section the reader is in. */
function useActiveSection(ids: string[]) {
  const [active, setActive] = useState(ids[0] ?? "");
  useEffect(() => {
    /* A section counts as current once its heading passes the upper third of
     * the viewport, which is where a reader's eye actually sits — keying off
     * intersection with the whole viewport makes the marker jump to whichever
     * section happens to be tallest. */
    const onScroll = () => {
      let current = ids[0] ?? "";
      for (const id of ids) {
        const el = document.getElementById(id);
        if (el && el.getBoundingClientRect().top <= window.innerHeight / 3) {
          current = id;
        }
      }
      setActive(current);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [ids]);
  return active;
}

const NAV = [
  { id: "start", label: "Start here" },
  ...SECTIONS.map((s) => ({ id: s.id, label: s.title })),
  { id: "gaps", label: "Known gaps" },
];

export function DocsView() {
  const active = useActiveSection(NAV.map((n) => n.id));

  return (
    <div className="on-canvas min-h-screen bg-canvas font-sans text-on-canvas">
      <header className="sticky top-0 z-30 border-b border-on-canvas/15 bg-canvas/90 backdrop-blur-sm">
        <nav className="mx-auto flex max-w-[1180px] items-center justify-between px-6 py-4">
          <Link
            to="/"
            className="flex items-baseline gap-xs font-display text-sm uppercase tracking-marker text-on-canvas transition-colors hover:text-oxide-paper"
          >
            <span className="selected">MJ&nbsp;Research</span>
            <span className="text-label text-on-canvas-faint">Reference</span>
          </Link>
          <Link
            to="/dashboard"
            aria-label="Open the dashboard"
            className="bg-enamel px-4 py-2 font-display text-label uppercase tracking-marker text-on-accent-light transition-colors hover:bg-oxide-paper focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-oxide-paper"
          >
            Open&nbsp;→
          </Link>
        </nav>
      </header>

      <div className="mx-auto flex max-w-[1180px] gap-3xl px-6 py-3xl">
        {/* Contents. Sticky on wide screens, dropped entirely on narrow ones —
          * a rail that becomes a stack of links above the document is just the
          * document's own headings printed twice. */}
        {/* `max-h` + `overflow-y-auto` are not decoration: docs.ts is required to
          * grow a section per feature, and a sticky element that overflows the
          * viewport cannot be page-scrolled to — the tail would simply become
          * unreachable. */}
        <aside className="sticky top-24 hidden h-fit max-h-[calc(100vh-7rem)] w-[210px] shrink-0 overflow-y-auto overscroll-contain lg:block">
          <p className="mb-sm font-display text-label uppercase tracking-label text-on-canvas-faint">
            Contents
          </p>
          <ul className="flex flex-col gap-2xs border-l border-on-canvas/15">
            {NAV.map((n) => (
              <li key={n.id}>
                <a
                  href={`#${n.id}`}
                  className={clsx(
                    "-ml-px block border-l-2 py-2xs pl-sm text-body-xs transition-colors focus-visible:outline-none focus-visible:text-enamel focus-visible:underline",
                    active === n.id
                      ? "border-oxide-paper text-enamel"
                      : "border-transparent text-on-canvas-soft hover:text-enamel",
                  )}
                  aria-current={active === n.id ? "true" : undefined}
                >
                  {n.label}
                </a>
              </li>
            ))}
          </ul>
        </aside>

        <main className="min-w-0 flex-1">
          <section id="start" className="scroll-mt-24">
            <p className="font-display text-label uppercase tracking-marker text-oxide-paper">
              Reference
            </p>
            <h1 className="mt-md max-w-[24ch] font-display text-[clamp(32px,4.5vw,52px)] leading-[1.05] tracking-tight text-enamel">
              What it computes, and what it writes.
            </h1>
            <p className="mt-xl max-w-measure text-body-lg text-on-canvas-soft">
              {OPENING.oneLine}
            </p>
            <p className="mt-lg max-w-measure text-body text-on-canvas-soft">
              {OPENING.thesis}
            </p>

            {/* The legend, up front. Every label used below is defined here
              * once, so a reader who starts in the middle can come back to
              * one place rather than inferring four conventions. */}
            <div className="mt-2xl border-t-2 border-enamel/25 pt-lg">
              <p className="font-display text-label uppercase tracking-label text-on-canvas-faint">
                How to read the labels
              </p>
              <dl className="mt-md flex flex-col gap-md">
                {(Object.keys(TRUST_META) as Trust[]).map((t) => (
                  <div key={t} className="flex flex-col gap-2xs sm:flex-row sm:gap-md">
                    <dt className="shrink-0 sm:w-[210px]">
                      <TrustChip trust={t} />
                    </dt>
                    <dd className="max-w-measure text-body-sm text-on-canvas-soft">
                      {TRUST_META[t].meaning}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          </section>

          {SECTIONS.map((s) => (
            <section
              key={s.id}
              id={s.id}
              className="mt-3xl scroll-mt-24 border-t border-enamel/15 pt-2xl"
            >
              <h2 className="font-display text-title-md tracking-tight text-enamel">
                {s.title}
              </h2>
              <p className="mt-xs max-w-measure text-body-sm italic text-on-canvas-faint">
                {s.standfirst}
              </p>

              {s.items && (
                <ul className="mt-xl flex flex-col">
                  {s.items.map((it) => (
                    <li
                      key={it.name}
                      className="border-b border-enamel/12 py-lg first:border-t first:border-enamel/12"
                    >
                      <div className="flex flex-wrap items-baseline justify-between gap-sm">
                        <h3 className="text-title-xs font-semibold text-enamel">
                          {it.name}
                        </h3>
                        <TrustChip trust={it.trust} />
                      </div>
                      <p className="mt-xs max-w-measure text-body-sm text-on-canvas-soft">
                        {it.detail}
                      </p>
                    </li>
                  ))}
                </ul>
              )}

              {s.body.length > 0 && (
                <div className={clsx("flex flex-col gap-md", s.items ? "mt-xl" : "mt-lg")}>
                  {s.body.map((p) => (
                    <p key={p.slice(0, 40)} className="max-w-measure text-body text-on-canvas-soft">
                      {p}
                    </p>
                  ))}
                </div>
              )}
            </section>
          ))}

          <section
            id="gaps"
            className="mt-3xl scroll-mt-24 border-t-2 border-oxide-paper pt-2xl"
          >
            <h2 className="font-display text-title-md tracking-tight text-enamel">
              Known gaps
            </h2>
            <p className="mt-xs max-w-measure text-body-sm italic text-on-canvas-faint">
              Ordered by how likely each one is to mislead someone, not by how
              comfortable it is to admit.
            </p>
            <div className="mt-xl flex flex-col gap-lg">
              {GAPS.map(([title, body], i) => (
                <div key={title} className="grid grid-cols-[auto_1fr] gap-md">
                  <span className="font-display text-label tabular text-oxide-paper">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div>
                    <h3 className="text-title-xs font-semibold text-enamel">
                      {title}
                    </h3>
                    <p className="mt-2xs max-w-measure text-body-sm text-on-canvas-soft">
                      {body}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <footer className="mt-3xl border-t border-enamel/20 pt-xl">
            <p className="max-w-measure text-body-sm text-on-canvas-soft">
              A personal research tool — not investment advice. The source is on{" "}
              <a
                href="https://github.com/karanmjpinto/mjresearch"
                target="_blank"
                rel="noreferrer"
                className="text-oxide-paper underline decoration-oxide-paper/40 underline-offset-4 transition-colors hover:decoration-oxide-paper focus-visible:outline-none focus-visible:decoration-oxide-paper"
              >
                GitHub
              </a>
              .
            </p>
          </footer>
        </main>
      </div>
    </div>
  );
}
