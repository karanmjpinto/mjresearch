import { AppNav } from "./AppNav";
import { SectionCard } from "./SectionCard";
import { SECTIONS } from "@/lib/sections";

/**
 * The front door. Four choices, and deliberately nothing else.
 *
 * What is NOT on this screen is the design. No portfolio value, no market
 * summary, no recent runs, no watchlist — all of which exist one click away
 * on the Dashboard and all of which were on the first screen before. A
 * number on the entry screen is an answer to a question you have not asked
 * yet, and the cost of showing it is that the four things you might actually
 * want to *do* have to compete with it for the first second of attention.
 *
 * So: the question each section answers, in the first person, and a way in.
 * Everything deeper is reached by choosing, not by scrolling.
 */
export function AppHome() {
  return (
    <div className="min-h-screen bg-ink">
      <AppNav active="home" />
      <main className="mx-auto max-w-4xl px-md py-xl sm:px-lg sm:py-2xl">
        <header className="mb-lg sm:mb-xl">
          <h1 className="font-display text-display-md text-bone">
            What are you doing?
          </h1>
          <p className="mt-xs max-w-[60ch] text-sm leading-relaxed text-on-ink-soft">
            Four things happen at this desk. Pick one — everything else is
            inside.
          </p>
        </header>

        {/* A single column on purpose. Four cards in a 2×2 grid read as a
          * dashboard of equal tiles; in a column they read as an ordered
          * list of stages, which is what they are: you find, then evaluate,
          * then manage. Setup is last because you do it once. */}
        <div className="flex flex-col gap-sm">
          {SECTIONS.map((s) => (
            <SectionCard
              key={s.key}
              to={s.to}
              num={s.num}
              label={s.label}
              blurb={s.question}
            />
          ))}
        </div>
      </main>
    </div>
  );
}
