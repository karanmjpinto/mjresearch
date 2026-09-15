/**
 * Printed ephemera, drawn in the same 1-bit register as the display face.
 *
 * The landing page argues that a figure comes from code and can be checked. An
 * argument made only in prose is a claim; the same argument as an object you
 * can read — a run record with its snapshot hash and its count of unverifiable
 * claims — is evidence. So these are not decoration borrowed from a mood board:
 * each one depicts something the system actually produces.
 *
 * They are HTML rather than SVG wherever they carry words, so the text is real
 * text — selectable, searchable, and set in the same font as everything else.
 * SVG is reserved for pure ornament, where there is nothing to read.
 */

import clsx from "clsx";

/**
 * Perforated edges.
 *
 * A radial-gradient mask punches the notches out of the top and bottom edges at
 * a fixed pitch. The pitch is a whole number of pixels because a half-pixel
 * notch renders as a smudge at exactly the size these are used.
 */
// The `#000` below is a mask, where only the alpha channel is read: black means
// "keep this pixel". It is not a colour, has no themeable counterpart, and
// swapping it for a palette token would change nothing but the spelling.
const PERFORATED: React.CSSProperties = {
  WebkitMaskImage:
    "radial-gradient(circle 4px at 8px 0, transparent 98%, #000 100%), radial-gradient(circle 4px at 8px 100%, transparent 98%, #000 100%)",
  maskImage:
    "radial-gradient(circle 4px at 8px 0, transparent 98%, #000 100%), radial-gradient(circle 4px at 8px 100%, transparent 98%, #000 100%)",
  WebkitMaskSize: "16px 100%, 16px 100%",
  maskSize: "16px 100%, 16px 100%",
  WebkitMaskRepeat: "repeat-x, repeat-x",
  maskRepeat: "repeat-x, repeat-x",
  WebkitMaskComposite: "source-in",
  maskComposite: "intersect",
};

function Rule() {
  return <div aria-hidden className="my-xs border-t border-dashed border-enamel/25" />;
}

function Row({ k, v, tone }: { k: string; v: string; tone?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-md">
      <span className="text-on-canvas-faint">{k}</span>
      <span className={clsx("tabular", tone ?? "text-enamel")}>{v}</span>
    </div>
  );
}

/**
 * A run record as a till receipt.
 *
 * Every field here is one the harness genuinely persists, and the two lines
 * that matter most are the last two: a count of claims it could not map, and
 * whether a second run of the same inputs agreed. A tool that printed only the
 * first eleven lines would be the thing this project was built to argue with.
 */
export function RunTape({ className }: { className?: string }) {
  return (
    <div
      className={clsx(
        "w-[210px] shrink-0 bg-paper px-md py-lg font-display text-label leading-[1.9] shadow-[3px_3px_0_0_rgba(31,27,23,0.16)]",
        className,
      )}
      style={PERFORATED}
    >
      <div className="text-center uppercase tracking-marker text-enamel">MJ Research</div>
      <div className="text-center uppercase tracking-marker text-on-canvas-faint">Run record</div>
      <Rule />
      <Row k="TICKER" v="AAPL" />
      <Row k="SNAPSHOT" v="3f9a2c" />
      <Row k="PLAN" v="7 NODES" />
      <Row k="MODEL" v="qwen3:30b" />
      <Row k="TEMP" v="0.00" />
      <Rule />
      <Row k="CLAIMS" v="14" />
      <Row k="CHECKED" v="12" tone="text-verdigris" />
      <Row k="UNVERIFIABLE" v="2" tone="text-oxide" />
      <Rule />
      <div className="flex items-baseline justify-between gap-md">
        <span className="text-on-canvas-faint">REPLAY</span>
        <span className="tabular text-verdigris">AGREES</span>
      </div>
    </div>
  );
}

/**
 * A density ramp — the printer's own test strip.
 *
 * Four tones a 1-bit screen can actually hold, in order. It doubles as the
 * legend for every other dithered surface on the page.
 */
export function DensityPlate({ className }: { className?: string }) {
  const steps: Array<[string, string]> = [
    ["0", ""],
    ["12", "dither-12"],
    ["25", "dither-25"],
    ["50", "dither-50"],
    ["100", "bg-enamel"],
  ];
  return (
    <div className={clsx("w-[168px] shrink-0", className)}>
      <div className="mb-2xs flex font-display text-label uppercase tracking-marker text-on-canvas-faint">
        <span>Density</span>
      </div>
      <div className="flex border border-enamel/30">
        {steps.map(([label, cls]) => (
          <div key={label} className="flex-1 border-r border-enamel/20 last:border-r-0">
            <div className={clsx("h-10 text-enamel", cls)} />
            <div className="border-t border-enamel/20 py-2xs text-center font-display text-label tabular text-on-canvas-faint">
              {label}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * A registration mark, as printed in the margin of a plate that has to line up
 * with the three below it. Purely ornamental — hence SVG, and hence hidden.
 */
export function RegistrationMark({
  className,
  size = 22,
}: {
  className?: string;
  size?: number;
}) {
  return (
    <svg
      aria-hidden
      width={size}
      height={size}
      viewBox="0 0 22 22"
      shapeRendering="crispEdges"
      className={className}
    >
      <g fill="none" stroke="currentColor" strokeWidth="1">
        <path d="M11 0v7M11 15v7M0 11h7M15 11h7" />
        <circle cx="11" cy="11" r="4.5" />
      </g>
    </svg>
  );
}

/**
 * The glyphs this interface actually leans on, set at a size where the bitmap
 * grid is visible. A specimen sheet for a page that is itself an argument about
 * numerals.
 */
export function GlyphPlate({ className }: { className?: string }) {
  return (
    <div className={clsx("w-[240px] shrink-0", className)}>
      <div className="mb-xs flex items-baseline justify-between font-display text-label uppercase tracking-marker text-on-canvas-faint">
        <span>Specimen</span>
        <span className="tabular">12/72</span>
      </div>
      <div className="border border-enamel/25 bg-paper/70 p-md">
        <div className="font-display text-specimen tracking-tight text-enamel">
          0123456789
        </div>
        <div className="mt-2xs font-display text-specimen tracking-tight text-oxide">
          +−%×↑↓
        </div>
      </div>
    </div>
  );
}
