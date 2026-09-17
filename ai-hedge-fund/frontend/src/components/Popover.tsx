import { useEffect, useId, useRef, useState } from "react";

/**
 * The small "i" marker and the panel it opens.
 *
 * Written once because it was written three times. The glossary tips, the
 * driver guidance and the persona notes each need the same five behaviours,
 * and each got them slightly differently — one of them used `<details>`, which
 * expands in normal flow and pushed the card's own heading sideways.
 *
 * Five things, all of which were bugs before they were features:
 *
 *   floats          absolutely positioned, so opening it never reflows the
 *                   layout it sits in
 *   picks a side    measured against the window on open. A marker in a
 *                   right-hand column opened a panel that ran off screen.
 *   resets type     these markers live inside `font-display uppercase
 *                   tracking-label` headings, and a child inherits all three.
 *                   A paragraph of explanation in a 1-bit bitmap face, in
 *                   capitals, is the least readable text in the app.
 *   closes          Escape, an outside press, or the marker again — and
 *                   Escape returns focus to the marker rather than dropping
 *                   the reader at the top of the document.
 *   announces       a real `button` with an accessible name, not a hover
 *                   tooltip, which cannot be reached by keyboard or touch.
 *
 * `mousedown` rather than `click` for the outside press: a click listener
 * fires after the button's own handler has toggled, so pressing the marker to
 * close would close and immediately reopen.
 */

type Props = {
  /** The button's accessible name — a question, since that is what it answers. */
  label: string;
  /** Panel width in rem, clamped to the viewport. */
  width?: number;
  children: React.ReactNode;
};

/** Gap between the marker and the panel — `top-6` / `bottom-6`, in px. */
const OFFSET = 24;
/** Breathing room kept against the window edge. */
const MARGIN = 16;
/** Below this, opening downward is not worth it; look up instead. */
const MIN_USABLE = 200;

export function Popover({ label, width = 20, children }: Props) {
  const [open, setOpen] = useState(false);
  const [side, setSide] = useState<"start" | "end">("start");
  const [place, setPlace] = useState<"below" | "above">("below");
  const [maxH, setMaxH] = useState<number | null>(null);
  const wrap = useRef<HTMLSpanElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;

    const fit = () => {
      const rect = wrap.current?.getBoundingClientRect();
      if (!rect) return;
      const px = Math.min(window.innerWidth - 32, width * 16);
      setSide(rect.left + px > window.innerWidth - 16 ? "end" : "start");

      /* Vertical fit, which this did not do and needed to.
       *
       * Panels used to be three short lines, so anywhere below the marker was
       * fine. Then the investor panel started listing what each investor
       * checks and grew to about 680px — taller than the room under a marker
       * halfway down the page — and ran clean off the bottom of the window
       * with no way to reach the rest. The browser will not scroll to it
       * either: the panel is absolutely positioned, so it adds no height to
       * the document.
       *
       * Two moves, in order: open upward when there is more room up there,
       * then cap the height to whatever room the chosen direction actually
       * has and let the panel scroll inside itself. The cap is what makes
       * this safe at any trigger position, so it applies in both directions
       * rather than only the one that overflowed. */
      const below = window.innerHeight - rect.bottom - OFFSET - MARGIN;
      const above = rect.top - OFFSET - MARGIN;
      const up = below < MIN_USABLE && above > below;
      setPlace(up ? "above" : "below");
      setMaxH(Math.max(MIN_USABLE, up ? above : below));
    };

    fit();

    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      wrap.current?.querySelector("button")?.focus();
    };
    const onDown = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };

    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    /* Re-measured while open, because the measurement goes stale the moment
     * anything moves. The panel is absolutely positioned and so adds no
     * height to the document: a cap computed for the old scroll position
     * leaves the panel hanging off the window again, with nothing to scroll
     * to it. Passive, since neither handler blocks the gesture. */
    window.addEventListener("scroll", fit, { passive: true, capture: true });
    window.addEventListener("resize", fit, { passive: true });
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("scroll", fit, { capture: true });
      window.removeEventListener("resize", fit);
    };
  }, [open, width]);

  return (
    <span ref={wrap} className="relative inline-flex align-middle">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        aria-label={label}
        className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border font-display text-[10px] leading-none transition-colors focus-visible:outline-none ${
          open
            ? "border-cobalt text-cobalt"
            : "border-ink-line text-on-ink-faint hover:border-cobalt hover:text-cobalt focus-visible:border-cobalt focus-visible:text-cobalt"
        }`}
      >
        i
      </button>

      {open && (
        <span
          id={panelId}
          role="note"
          /* A `span` with block children throughout: this renders inside
           * headings, labels, paragraphs and table cells, and a `div` in a
           * `p` is invalid markup that browsers silently reflow. */
          className={`absolute z-50 flex flex-col gap-xs overflow-y-auto overscroll-contain border border-ink-line bg-ink-raised p-sm font-sans normal-case tracking-normal shadow-elev-2 ${
            side === "end" ? "right-0" : "left-0"
          } ${place === "above" ? "bottom-6" : "top-6"}`}
          style={{
            width: `min(${width}rem, calc(100vw - 2rem))`,
            maxHeight: maxH != null ? `${maxH}px` : undefined,
          }}
        >
          {children}
        </span>
      )}
    </span>
  );
}
