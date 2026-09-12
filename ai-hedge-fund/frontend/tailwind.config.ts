import type { Config } from "tailwindcss";

/**
 * Palette and type read off Pollock's drip canvases — see src/index.css for
 * where the values come from. Tailwind names map to the CSS custom properties
 * so the two never drift apart.
 */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      /**
       * Literal OKLCH with the <alpha-value> placeholder, NOT `var(--token)`.
       * Tailwind composes opacity modifiers (`bg-canvas/92`) by substituting
       * that placeholder; given a bare `var()` it cannot, and silently emits an
       * invalid colour — the utility then resolves to transparent with no error.
       * The same values are mirrored as custom properties in src/index.css for
       * inline styles and non-Tailwind rules.
       */
      colors: {
        canvas: {
          DEFAULT: "oklch(92.5% 0.018 82 / <alpha-value>)",
          deep: "oklch(88% 0.024 80 / <alpha-value>)",
        },
        ink: {
          DEFAULT: "oklch(19% 0.012 60 / <alpha-value>)",
          raised: "oklch(24% 0.014 62 / <alpha-value>)",
          line: "oklch(32% 0.016 64 / <alpha-value>)",
        },
        oxide: "oklch(52% 0.166 32 / <alpha-value>)",
        cadmium: "oklch(78% 0.158 78 / <alpha-value>)",
        cobalt: "oklch(52% 0.174 258 / <alpha-value>)",
        verdigris: "oklch(58% 0.088 178 / <alpha-value>)",
        aluminium: "oklch(72% 0.012 80 / <alpha-value>)",
        bone: "oklch(96% 0.012 84 / <alpha-value>)",
        "on-canvas": {
          DEFAULT: "oklch(26% 0.018 62 / <alpha-value>)",
          soft: "oklch(46% 0.022 64 / <alpha-value>)",
          faint: "oklch(62% 0.020 66 / <alpha-value>)",
        },
        "on-ink": {
          DEFAULT: "oklch(92% 0.012 82 / <alpha-value>)",
          soft: "oklch(72% 0.014 76 / <alpha-value>)",
          faint: "oklch(54% 0.014 70 / <alpha-value>)",
        },

        /* Legacy names kept so views not yet reworked stay coherent
         * rather than falling back to Tailwind defaults. */
        surface: {
          DEFAULT: "oklch(19% 0.012 60 / <alpha-value>)",
          card: "oklch(24% 0.014 62 / <alpha-value>)",
          elevated: "oklch(32% 0.016 64 / <alpha-value>)",
        },
        border: {
          DEFAULT: "oklch(32% 0.016 64 / <alpha-value>)",
          light: "oklch(54% 0.014 70 / <alpha-value>)",
        },
        accent: {
          blue: "oklch(52% 0.174 258 / <alpha-value>)",
          green: "oklch(58% 0.088 178 / <alpha-value>)",
          red: "oklch(52% 0.166 32 / <alpha-value>)",
          yellow: "oklch(78% 0.158 78 / <alpha-value>)",
        },
      },
      fontFamily: {
        display: ['"Departure Mono"', "ui-monospace", "monospace"],
        mono: ['"Departure Mono"', "ui-monospace", "monospace"],
        sans: ['"Bricolage Grotesque"', "ui-sans-serif", "system-ui", "sans-serif"],
      },
      fontSize: {
        /* Whole pixels: the display face is a bitmap and blurs off-grid. */
        "display-xl": ["72px", { lineHeight: "1.02", letterSpacing: "-0.01em" }],
        "display-lg": ["56px", { lineHeight: "1.05", letterSpacing: "-0.01em" }],
        "display-md": ["36px", { lineHeight: "1.1" }],
        "display-sm": ["24px", { lineHeight: "1.15" }],

        /* The legibility floor for micro-labels. Below 12px uppercase
         * tracked type stops being reliably readable, and the bitmap face
         * has no hinting to fall back on. Named here so the floor is one
         * decision instead of seventy-five inline `text-[10px]` literals.
         * Size only, no lineHeight: these sit inside badges and flex rows
         * whose vertical rhythm is already set by their container. */
        label: "12px",

        /* Chrome marks: the wordmark and the active ticker. Whole pixels,
         * because both render in the bitmap face, and named because the scale
         * had nothing between `label` (12px) and `display-sm` (24px) — so the
         * two sat as inline literals and had already drifted a pixel apart
         * (15px and 16px) without anyone choosing that. One value now. */
        mark: "16px",

        /* Prose and card titles, in rem so a reader who has raised their
         * browser's base size gets larger text. The whole-pixel rule above
         * binds the bitmap face, not Bricolage: these never render in Departure
         * Mono, so there is no grid for them to fall off.
         *
         * These were spelled inline as
         * `text-[15px] leading-[1.65]` and friends at three dozen call sites on
         * the landing page alone, which is how a type scale quietly stops being
         * one. Size and leading travel together because changing one without
         * the other is always a mistake. */
        "body-lg": ["1.0625rem", { lineHeight: "1.65" }],
        body: ["1rem", { lineHeight: "1.7" }],
        "body-sm": ["0.9375rem", { lineHeight: "1.65" }],
        "body-xs": ["0.875rem", { lineHeight: "1.6" }],
        "title-sm": ["1.1875rem", { lineHeight: "1.3" }],
        "title-xs": ["1.0625rem", { lineHeight: "1.35" }],

        /* The chapter headings on the landing page. Fluid rather than a whole
         * pixel, which the note above warns against — at intermediate widths it
         * lands off-grid and the bitmap softens. That trade was already being
         * made at four call sites; naming it does not make it worse, and makes
         * the day someone wants it fixed a one-line day. */
        chapter: ["clamp(26px, 3vw, 38px)", { lineHeight: "1.1" }],

        /* Display type large enough that the bitmap grid is the point — the
         * glyph specimen. Whole pixels, like every other size in the face. */
        specimen: ["34px", { lineHeight: "1.15" }],
      },
      letterSpacing: {
        /* Tracking for the micro-labels that `fontSize.label` sets the size of.
         * The pair travels together — uppercase 12px needs the extra track to
         * stay readable — so it is named here rather than respelled as
         * `tracking-[0.1em]` at every call site. */
        label: "0.1em",

        /* The wider track for standalone uppercase markers — section eyebrows,
         * the wordmark, button labels. The landing page had reached four
         * near-identical values (0.14em, 0.16em, 0.18em, 0.2em) that nobody had
         * chosen between; they are one value now, because the differences were
         * invisible and the drift was not. */
        marker: "0.18em",
      },
      spacing: {
        "2xs": "var(--space-2xs)",
        xs: "var(--space-xs)",
        sm: "var(--space-sm)",
        md: "var(--space-md)",
        lg: "var(--space-lg)",
        xl: "var(--space-xl)",
        "2xl": "var(--space-2xl)",
        "3xl": "var(--space-3xl)",
        "4xl": "var(--space-4xl)",
      },
      transitionTimingFunction: {
        /* Exponential deceleration — things stop the way real objects do. */
        "out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
        "out-quart": "cubic-bezier(0.25, 1, 0.5, 1)",
      },
    },
  },
  plugins: [],
} satisfies Config;
