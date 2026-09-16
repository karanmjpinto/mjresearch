import { useId } from "react";

/**
 * A number you are expected to change.
 *
 * The complaint this exists to answer was specific: on a screen of figures it
 * was not obvious which boxes were inputs. Everything looked equally typed-in
 * and equally fixed. So an input here is built to be unmistakable, and the
 * cues are stacked rather than relying on any single one:
 *
 *   - it sits in a well — a recessed field on the raised card around it, which
 *     is the one place on the screen with that treatment
 *   - the border is a full box, not a bottom rule, and it turns cobalt on focus
 *   - the unit is printed inside the field, so nobody has to guess percent
 *     versus fraction, which is the actual error people make here
 *   - underneath, in plain words, where the starting number came from
 *
 * Read-only figures elsewhere are deliberately plain text on the card, with no
 * box at all. That contrast is the whole mechanism: one look should tell you
 * what you can move and what the model worked out.
 *
 * `derived` versus `required` is a real distinction and coloured as one. A
 * derived default is a starting point you may overrule; a required driver has
 * no defensible default at all, and the screen refuses to value the company
 * until it is supplied rather than quietly assuming a growth rate.
 */

export type DriverInputProps = {
  label: string;
  /** Raw text, so a half-typed "0." is not fought by the parser. */
  value: string;
  onChange: (next: string) => void;
  /** Printed inside the field: "%", "x", "yrs". */
  unit?: string;
  /** Where the starting number came from, in plain words. */
  because?: string;
  /** The derived default, for the reset affordance. */
  derived?: number | null;
  onReset?: () => void;
  /** No defensible default exists — the valuation waits for this. */
  required?: boolean;
  /** Set when the typed value is unusable. */
  invalid?: boolean;
  hint?: string;
  step?: string;
  /** The guidance marker, rendered beside the label. */
  help?: React.ReactNode;
};

export function DriverInput({
  label,
  value,
  onChange,
  unit,
  because,
  derived,
  onReset,
  required = false,
  invalid = false,
  hint,
  step = "any",
  help,
}: DriverInputProps) {
  const id = useId();
  const describedBy = `${id}-note`;
  const empty = value.trim() === "";
  const waiting = required && empty;

  return (
    <div className="flex flex-col gap-2xs">
      <label
        htmlFor={id}
        className="flex items-baseline gap-xs font-display text-label uppercase tracking-label text-on-ink-soft"
      >
        {label}
        {help}
        {required && (
          <span
            className="text-oxide"
            title="No default — this has to be supplied"
          >
            needs a number
          </span>
        )}
      </label>

      <div
        className={`flex items-center border bg-ink transition-colors focus-within:border-cobalt ${
          invalid || waiting ? "border-oxide" : "border-ink-line"
        }`}
      >
        <input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          inputMode="decimal"
          step={step}
          aria-invalid={invalid || waiting}
          aria-describedby={describedBy}
          placeholder={derived != null ? String(derived) : "—"}
          className="w-full min-w-0 bg-transparent px-sm py-1.5 font-display text-mark tabular text-bone outline-none placeholder:text-on-ink-faint"
        />
        {unit && (
          /* Inside the field, not after it: the unit is part of the value, and
           * a "%" floating outside gets read as decoration and ignored. */
          <span
            aria-hidden="true"
            className="shrink-0 border-l border-ink-line px-sm py-1.5 font-display text-label text-on-ink-faint"
          >
            {unit}
          </span>
        )}
      </div>

      <p
        id={describedBy}
        className={`max-w-[46ch] text-body-xs leading-snug ${
          invalid || waiting ? "text-cadmium" : "text-on-ink-faint"
        }`}
      >
        {invalid
          ? (hint ?? "That is not a number this can use.")
          : waiting
            ? (hint ??
              "Nothing sensible could be worked out, so it has to be typed.")
            : (because ?? " ")}
      </p>

      {onReset && derived != null && !empty && Number(value) !== derived && (
        <button
          type="button"
          onClick={onReset}
          className="self-start font-display text-label uppercase tracking-label text-on-ink-faint underline decoration-dotted transition-colors hover:text-cadmium"
        >
          Back to {derived}
          {unit ?? ""}
        </button>
      )}
    </div>
  );
}
