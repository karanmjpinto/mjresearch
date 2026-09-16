import { GLOSSARY, type GlossaryEntry, type GlossaryKey } from "@/lib/glossary";
import { Popover } from "./Popover";

/**
 * What this term means, one press away.
 *
 * The app is full of words that are precise and unfamiliar at the same time —
 * conviction, sector drift, sales to capital, terminal growth. Explaining them
 * in the surrounding prose would bury the screen; leaving them unexplained
 * makes a reader guess, and a guessed definition is worse than none because
 * nothing ever corrects it.
 *
 * The text lives in `lib/glossary.ts`, not here. One file means the same word
 * is explained the same way everywhere it appears, and improving a definition
 * is one edit. The floating and the keyboard handling live in `Popover`.
 */

type Props = {
  term: GlossaryKey;
  /** Overrides the glossary label in the button's accessible name. */
  label?: string;
};

export function InfoTip({ term, label }: Props) {
  // Widened on purpose: `as const satisfies` narrows each entry to its own
  // literal shape, so `why` and `careful` are absent from the union even
  // though the declared type allows them.
  const entry: GlossaryEntry | undefined = GLOSSARY[term];
  if (!entry) return null;

  return (
    <Popover label={`What does ${label ?? entry.term} mean?`} width={20}>
      <span className="block font-display text-label uppercase tracking-label text-cadmium">
        {entry.term}
      </span>
      <span className="block text-body-xs leading-relaxed text-on-ink">
        {entry.what}
      </span>
      {entry.why && (
        <span className="block border-t border-ink-line pt-xs text-body-xs leading-relaxed text-on-ink-soft">
          {entry.why}
        </span>
      )}
      {entry.careful && (
        /* The trap, where there is one. Usually the most valuable line: a
         * definition tells you what a number is, this tells you how it
         * misleads. */
        <span className="block border-t border-ink-line pt-xs text-body-xs leading-relaxed text-cadmium">
          {entry.careful}
        </span>
      )}
    </Popover>
  );
}
