import { Link } from "react-router-dom";
import clsx from "clsx";

/**
 * One choice, rendered big enough to be the only thing you read.
 *
 * Shared by the four-door home and the section hubs so a door is the same
 * object wherever it appears — the thing that changes between levels is how
 * many there are, not what one looks like. Two components drifting apart is
 * how a "simple first screen" becomes a second menu style to learn.
 *
 * A `planned` door is rendered, dimmed, and not a link. Hiding it would be
 * easier and worse: a menu that silently omits what is missing teaches the
 * reader that nothing is missing.
 */
export type SectionCardProps = {
  to: string;
  num?: string;
  label: string;
  blurb: string;
  status?: "live" | "planned";
};

export function SectionCard({
  to,
  num,
  label,
  blurb,
  status = "live",
}: SectionCardProps) {
  const planned = status === "planned";

  const body = (
    <>
      <div className="flex items-baseline gap-sm">
        {num && (
          <span
            className={clsx(
              "font-display text-label tabular tracking-marker",
              planned ? "text-on-ink-faint" : "text-cadmium",
            )}
          >
            {num}
          </span>
        )}
        <h2
          className={clsx(
            "font-display text-display-sm",
            planned ? "text-on-ink-faint" : "text-bone",
          )}
        >
          {label}
        </h2>
        {planned && (
          <span className="font-display text-label uppercase tracking-marker text-on-ink-faint">
            · soon
          </span>
        )}
      </div>
      <p
        className={clsx(
          "mt-xs max-w-[60ch] text-sm leading-relaxed",
          planned ? "text-on-ink-faint" : "text-on-ink-soft",
        )}
      >
        {blurb}
      </p>
    </>
  );

  /* `no-tap-grow` matters and is not decoration. The coarse-pointer rule in
   * index.css gives every `a[class]` a 44px minimum and switches it to
   * `inline-flex; align-items: center` so a short label centres in the
   * taller box. This card is already far taller than 44px and lays out its
   * own children, and inline-flex would put the heading and the blurb side
   * by side on a phone — the one device where that is unreadable. The opt-out
   * exists for exactly this case. */
  const shell =
    "no-tap-grow block border border-ink-line bg-ink-raised px-md py-md transition-colors sm:px-lg sm:py-lg";

  if (planned) {
    /* `aria-disabled` on a non-interactive element would be a lie — there is
     * no control here to disable. It is a described region instead, so a
     * screen reader reads the label and the reason and moves on. */
    /* No `opacity-60` here. The planned state is already carried by
     * `text-on-ink-faint` on both the heading and the blurb, and DESIGN.md is
     * explicit that text is a shade of its own ground — multiplying a token
     * chosen to sit near the AA floor pushes it under. The dashed border says
     * "not yet" without touching the text. */
    return <div className={clsx(shell, "border-dashed")}>{body}</div>;
  }

  return (
    <Link
      to={to}
      className={clsx(
        shell,
        "hover:border-cobalt focus-visible:border-cobalt focus-visible:outline-none",
      )}
    >
      {body}
    </Link>
  );
}
