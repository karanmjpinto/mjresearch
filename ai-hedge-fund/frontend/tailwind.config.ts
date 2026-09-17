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
       * `oklch(var(--token) / <alpha-value>)`, where each custom property in
       * src/index.css holds OKLCH *channels* rather than a finished colour.
       *
       * The <alpha-value> placeholder is what makes the opacity modifiers the
       * components already use (`bg-cadmium/10`, `border-border/60`) compose;
       * hand Tailwind a finished `var(--x)` and it cannot substitute, so it
       * emits an invalid colour and the utility resolves to transparent with
       * no error. Channels keep the placeholder AND let one name mean the
       * right thing in daylight and at night, which literals could not.
       *
       * So the names below are roles, not hues. `ink` is "the page" and
       * follows the theme; it is dark at night and near-white in daylight.
       * The one role that must NOT follow the theme is text sitting on a
       * coloured fill — a cadmium button is yellow in both themes — and that
       * lives in `on-accent`.
       */
      colors: {
        /* The landing page's linen band. Light in both themes, because it is
         * depicting paper rather than following the UI. */
        canvas: {
          DEFAULT: "oklch(var(--c-canvas) / <alpha-value>)",
          deep: "oklch(var(--c-canvas-deep) / <alpha-value>)",
        },
        "on-canvas": {
          DEFAULT: "oklch(var(--c-on-canvas) / <alpha-value>)",
          soft: "oklch(var(--c-on-canvas-soft) / <alpha-value>)",
          faint: "oklch(var(--c-on-canvas-faint) / <alpha-value>)",
        },
        paper: "oklch(var(--c-paper) / <alpha-value>)",
        /* The dark mark on that linen. Fixed, for the same reason `canvas` is:
         * the landing page is a composition on paper, not a themed surface, so
         * its rules and filled buttons stay enamel black in both themes. */
        enamel: "oklch(var(--c-enamel) / <alpha-value>)",

        /* The ground and the text on it. Both follow the theme. */
        ink: {
          DEFAULT: "oklch(var(--c-ground) / <alpha-value>)",
          raised: "oklch(var(--c-ground-raised) / <alpha-value>)",
          line: "oklch(var(--c-ground-line) / <alpha-value>)",
        },
        "on-ink": {
          DEFAULT: "oklch(var(--c-on-ground) / <alpha-value>)",
          soft: "oklch(var(--c-on-ground-soft) / <alpha-value>)",
          faint: "oklch(var(--c-on-ground-faint) / <alpha-value>)",
        },
        /* `bone` was "highlight white". It now means the strongest text the
         * ground allows, which is near-black in daylight. The name is
         * historical; 86 call sites use it correctly as "the brightest text",
         * and that reading still holds. */
        bone: "oklch(var(--c-strong) / <alpha-value>)",

        oxide: "oklch(var(--c-oxide) / <alpha-value>)",
        cadmium: "oklch(var(--c-cadmium) / <alpha-value>)",
        cobalt: "oklch(var(--c-cobalt) / <alpha-value>)",
        verdigris: "oklch(var(--c-verdigris) / <alpha-value>)",

        /* Accents for the linen ground, which stays light in both themes.
         * See the note in index.css: the theme-following accents above go
         * lighter for dark and lose their contrast against paper. Any page
         * built on `bg-canvas` wants these. */
        "oxide-paper": "oklch(var(--c-oxide-paper) / <alpha-value>)",
        "cadmium-paper": "oklch(var(--c-cadmium-paper) / <alpha-value>)",
        "cobalt-paper": "oklch(var(--c-cobalt-paper) / <alpha-value>)",
        "verdigris-paper": "oklch(var(--c-verdigris-paper) / <alpha-value>)",
        aluminium: "oklch(var(--c-aluminium) / <alpha-value>)",

        /* Text on a coloured fill — fixed in both themes. `on-accent` for
         * bright paint (cadmium, verdigris), `on-accent-light` for deep
         * paint (oxide, cobalt). */
        "on-accent": {
          DEFAULT: "oklch(var(--c-on-accent) / <alpha-value>)",
          light: "oklch(var(--c-on-accent-light) / <alpha-value>)",
        },

        /* Legacy names kept so views not yet reworked stay coherent rather
         * than falling back to Tailwind defaults. They point at the same
         * theme-aware roles. */
        surface: {
          DEFAULT: "oklch(var(--c-ground) / <alpha-value>)",
          card: "oklch(var(--c-ground-raised) / <alpha-value>)",
          elevated: "oklch(var(--c-ground-line) / <alpha-value>)",
        },
        border: {
          DEFAULT: "oklch(var(--c-ground-line) / <alpha-value>)",
          light: "oklch(var(--c-on-ground-faint) / <alpha-value>)",
        },
        accent: {
          blue: "oklch(var(--c-cobalt) / <alpha-value>)",
          green: "oklch(var(--c-verdigris) / <alpha-value>)",
          red: "oklch(var(--c-oxide) / <alpha-value>)",
          yellow: "oklch(var(--c-cadmium) / <alpha-value>)",
        },

        /* Stock Tailwind neutrals, overridden rather than chased out of 15
         * files one class at a time. `text-gray-500` appears 180 times and
         * means "muted secondary text"; a fixed mid-grey means that in the
         * dark and means nothing in daylight, so the scale is remapped onto
         * the theme's own steps. The separate sweep converting these call
         * sites to named tokens is still the right cleanup — this keeps them
         * legible in both themes until it lands.
         *
         * `white` is remapped for the same reason: `text-white` (81 uses)
         * means "the strongest text", not the colour white. */
        gray: {
          100: "oklch(var(--c-strong) / <alpha-value>)",
          200: "oklch(var(--c-strong) / <alpha-value>)",
          300: "oklch(var(--c-on-ground) / <alpha-value>)",
          400: "oklch(var(--c-on-ground-soft) / <alpha-value>)",
          500: "oklch(var(--c-on-ground-soft) / <alpha-value>)",
          600: "oklch(var(--c-on-ground-faint) / <alpha-value>)",
          700: "oklch(var(--c-ground-line) / <alpha-value>)",
        },
        white: "oklch(var(--c-strong) / <alpha-value>)",
        /* `bg-black/20` is used as a recessed well, not as the colour black.
         * At night that is a darker tint; in daylight a light one would
         * disappear, so it stays a dark tint at low alpha either way. */
        black: "oklch(var(--c-scrim) / <alpha-value>)",
      },
      fontFamily: {
        display: ['"Departure Mono"', "ui-monospace", "monospace"],
        mono: ['"Departure Mono"', "ui-monospace", "monospace"],
        sans: [
          '"Bricolage Grotesque"',
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
      },
      /* Line length, named.
       *
       * `max-w-[72ch]` appeared thirty-six times across ten files — the
       * app's measure for running text, re-decided by hand at every call
       * site. One token means changing the measure is one line, and a
       * narrower variant exists for the places that need it (a table cell
       * carrying a sentence cannot take the full measure without swallowing
       * the table's slack and out-running every paragraph beside it). */
      maxWidth: {
        measure: "72ch",
        "measure-sm": "52ch",
      },

      fontSize: {
        /* Whole pixels: the display face is a bitmap and blurs off-grid. */
        "display-xl": [
          "72px",
          { lineHeight: "1.02", letterSpacing: "-0.01em" },
        ],
        "display-lg": [
          "56px",
          { lineHeight: "1.05", letterSpacing: "-0.01em" },
        ],
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
        "title-sm": ["1.375rem", { lineHeight: "1.3" }],
        "title-xs": ["1.1875rem", { lineHeight: "1.35" }],

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
      /* One declared light, from src/index.css. Named `elev` rather than
       * `shadow` because the point is which surfaces sit above the ground,
       * not that they have a shadow. */
      boxShadow: {
        "elev-1": "var(--elev-1)",
        "elev-2": "var(--elev-2)",
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
