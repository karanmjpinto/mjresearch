# Design System — MJ Research (AI Hedge Fund)

Source of truth for values: `frontend/src/index.css` (custom properties) and
`frontend/tailwind.config.ts` (the Tailwind names that mirror them). This file
explains the intent; those two files hold the numbers. If they disagree with
this document, the code is right and this document is stale — fix it.

## Product Context

- **What this is:** A local-first financial research and portfolio desk: market data, fundamentals, technicals, AI-assisted thesis (Ollama), and a SQLite-backed portfolio with risk.
- **Who it's for:** You and power users who live in tickers, tables, and charts — not casual retail onboarding flows.
- **Space/industry:** Fintech / research terminal (peers: Koyfin-style density, Bloomberg-adjacent seriousness without the terminal chrome).
- **Project type:** Web app with two grounds — a linen-ground marketing landing, a dark-ground working desk.

## Aesthetic Direction

**Read off Pollock's drip canvases.** *Autumn Rhythm* and *Number 1A* are not
colourful in the neon sense: they are unbleached linen with household enamel
thrown at it — oxide red, cadmium yellow, cobalt, aluminium, and a great deal of
black. The excitement comes from collision and density, not saturation. That is
why this palette stays earthy and still reads loud.

- **Direction:** Industrial / painterly — data-first, low ornament, confidence from clarity and density.
- **Decoration level:** Minimal in the desk; the landing carries the drip artwork and is the one place texture is the point.
- **Mood:** Calm, precise, made-not-generated. A tool for decisions, not a marketing page for one.
- **Anti-goal:** The purple-gradient "AI product" look. Risk and seriousness live in typography and data density, not in a glow.

## The two grounds

The single most structural decision here. Every surface is either **canvas**
(raw linen, dark text) or **ink** (enamel black, light text). Text colour is
always a shade of its own ground — never grey-on-colour.

| Ground | Background | Text | Where |
|---|---|---|---|
| canvas | `--canvas`, `--canvas-deep` | `--on-canvas` / `-soft` / `-faint` | Landing, print-like reading surfaces |
| ink | `--ink`, `--ink-raised`, `--ink-line` | `--on-ink` / `-soft` / `-faint` | The app: dashboard, research, portfolio |

Wrap a canvas-ground region in `.on-canvas` so its scrollbar flips too, instead
of punching a dark hole in the linen.

## Typography

- **Display, labels, numerals:** **Departure Mono** — Helena Zhang, SIL OFL 1.1, [departuremono.com](https://departuremono.com). Self-hosted (`/fonts/DepartureMono-Regular.woff2`), preloaded, licence in `/fonts/DepartureMono-LICENSE.txt`.
- **Body / prose:** **Bricolage Grotesque** (Google Fonts, optical size 12–96, weights 400/500/600/800).
- **It is a 1-bit bitmap face.** Two consequences, both non-negotiable: sizes must be **whole pixels** (integers, never fluid `clamp()`) or the bitmap softens; and font smoothing is turned **off** for `.font-display` / `.font-mono`, because antialiasing a 1-bit font just makes it look broken.
- **Numerals:** the `.tabular` utility (`font-variant-numeric: tabular-nums`) everywhere numbers are compared down a column. Defined in `index.css` — it is a local class, not a Tailwind one.

**Scale** (`tailwind.config.ts` → `fontSize`):

| Name | Size | Line height |
|---|---|---|
| `display-xl` | 72px | 1.02, `-0.01em` |
| `display-lg` | 56px | 1.05, `-0.01em` |
| `display-md` | 36px | 1.1 |
| `display-sm` | 24px | 1.15 |
| `label` | **12px** | — (inherits) |

**12px is the legibility floor.** Below it, uppercase tracked type stops being
reliably readable and the bitmap face has no hinting to fall back on. The floor
lives in `fontSize.label` precisely so it is one decision — reach for
`text-label`, never an inline `text-[10px]` or `text-[11px]`.

## Color

All values are **OKLCH**, so lightness steps are perceptually even.

**Grounds**

| Token | Value | Note |
|---|---|---|
| `--canvas` | `oklch(92.5% 0.018 82)` | raw linen, the landing ground |
| `--canvas-deep` | `oklch(88% 0.024 80)` | shadowed linen |
| `--ink` | `oklch(19% 0.012 60)` | enamel black, warm not blue |
| `--ink-raised` | `oklch(24% 0.014 62)` | lifted panel |
| `--ink-line` | `oklch(32% 0.016 64)` | hairline on dark |

**The thrown colours**

| Token | Value | Note |
|---|---|---|
| `--oxide` | `oklch(52% 0.166 32)` | rust red — loss, danger, destructive |
| `--cadmium` | `oklch(78% 0.158 78)` | cadmium yellow — caution, selection |
| `--cobalt` | `oklch(52% 0.174 258)` | ultramarine — links, focus, active |
| `--verdigris` | `oklch(58% 0.088 178)` | the occasional green — gain, pass |
| `--aluminium` | `oklch(72% 0.012 80)` | silver enamel |
| `--bone` | `oklch(96% 0.012 84)` | highlight white, **never `#fff`** |

**Text on ground:** `--on-canvas` 26% / `-soft` 46% / `-faint` 62%; `--on-ink`
92% / `-soft` 72% / `-faint` 54%.

Three rules:

1. **No hex in components, and no stock Tailwind greys.** `text-gray-500`, `#3B82F6` and friends are invisible to this system and render off-palette. Use the tokens.
2. **Tailwind mirrors these as literal OKLCH with the `<alpha-value>` placeholder, not `var(--token)`.** Tailwind composes opacity modifiers (`bg-canvas/92`) by substituting that placeholder; given a bare `var()` it cannot, and silently emits an invalid colour that resolves to transparent with no error.
3. **Canvas-rendered things read tokens at runtime.** `<canvas>` cannot take `var()`. `PriceChart` calls `getComputedStyle(document.documentElement).getPropertyValue('--oxide')` rather than hardcoding, so the chart moves with the palette.

`surface`, `border` and `accent-*` remain in the Tailwind config as **legacy
aliases** pointing at the same values, so views not yet reworked stay coherent
instead of falling back to Tailwind defaults. Do not reach for them in new work.

**Selection:** cadmium ground, ink text.

## Spacing

- **Scale** (`--space-*`, exposed as Tailwind spacing names): `2xs` 4 / `xs` 8 / `sm` 12 / `md` 16 / `lg` 24 / `xl` 32 / `2xl` 48 / `3xl` 64 / `4xl` 96.
- **Density:** Compact. This is a desk, not a landing page — prioritise rows visible without crowding touch targets.
- Use the semantic names (`gap-sm`, `mt-2xs`), not raw Tailwind numbers, so density is adjustable in one place.

## Layout

- **Approach:** Hybrid — grid-disciplined for portfolio tables and research metrics; a single measured column for long thesis prose.
- **Measure:** long-form text is capped in `ch`, not pixels (`max-w-[72ch]`, `max-w-[80ch]`), so the measure holds as type scales.
- **Desk width:** `max-w-6xl` / `max-w-7xl` for main content; full bleed only for charts where it earns it.
- **Radius:** Tailwind's defaults, used consistently rather than a bespoke scale — `rounded-xl` (12px) for cards and panels, `rounded-lg` (8px) for inner blocks, `rounded` (4px) for chips and inputs, `rounded-full` for pills.
- **Viewport height:** use `h-dvh`, not `h-screen`. `100vh` measures the viewport *including* mobile Safari's toolbar and clips the bottom of the scroll area.

## Motion

- **Approach:** Minimal-functional. Short fades on state change; no motion on numbers.
- **Easing:** `ease-out-expo` `cubic-bezier(0.16, 1, 0.3, 1)` and `ease-out-quart` `cubic-bezier(0.25, 1, 0.5, 1)` — exponential deceleration, so things stop the way real objects do.
- **Duration:** 300ms for most transitions; 1000ms reserved for the conviction gauge sweep.
- **Reduced motion:** less *movement*, not less feedback. `prefers-reduced-motion: reduce` kills animation and anything that travels across the screen, but keeps colour and opacity transitions at 120ms — those are how a user tracks that something responded, and they do not trigger vestibular symptoms. Implemented by restricting `transition-property` rather than zeroing `transition-duration`.

## Known drift

Not yet on the system, tracked here so it is not mistaken for intent:

- **Chart series palettes.** `OptimizeView` and `ResearchReport` still carry the old system's hex directly (`#3b82f6`, `#22c55e`, `#f59e0b`, `#ef4444`, `#38bdf8`, …) for Recharts series, weight bars and radar fills. This is not a mechanical swap: those arrays need up to ten categorically distinct colours and the palette has six, so a series ramp has to be *designed* — likely lightness/chroma steps off oxide–cadmium–cobalt–verdigris rather than ten unrelated hues. Until then the charts are visibly on the old blue.
- `PriceChart` **is** converted, and shows the pattern to follow: read tokens off `:root` at mount, since canvas cannot take `var()`.

## Accessibility

- 12px type floor (above); tokens keep text-on-ground contrast in a known range.
- Never encode meaning in colour alone — BUY/HOLD/SELL and P&L direction need a text or shape cue as well as an oxide/verdigris fill.
- Inputs need a real label or `aria-label`; a placeholder is not a label — it vanishes on first keystroke.

## Review loop

Design review runs on [Rams](https://rams.ai) at three levels: MCP tools in the
editor, a `PostToolUse` hook (`.claude/hooks/rams-loop.sh`) that fires on any
frontend UI edit, and a `design` job in CI gated on criticals. See the root
`CLAUDE.md` for the rules — notably that findings get fixed without asking, that
the loop is bounded at one fix pass, and that **`tailwind.config.ts` and
`src/index.css` must be sent with every review** or the reviewer grades against
stock Tailwind and reports false positives.

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-30 | Initial design system | `/design-consultation` aligned to existing MJ Research dark desk + fintech conventions |
| 2026-03-30 | Single accent (blue) | Avoid purple-gradient "AI product" cliché; risks live in typography + data density instead |
| 2026-08-22 | **Superseded by the Pollock system** | DM Sans / JetBrains Mono / `#3b82f6` on near-black was replaced in the code by Departure Mono + Bricolage Grotesque on the linen-and-enamel palette. This document had described the old system for months while the app shipped the new one; rewritten to match what is built. |
| 2026-08-22 | Two grounds, not one dark mode | The landing is linen and the desk is ink. Text is always a shade of its own ground, which is what keeps the drip artwork and the data density in the same world. |
| 2026-08-22 | OKLCH, not hex | Perceptually even lightness steps, and the `<alpha-value>` placeholder makes opacity modifiers work in Tailwind. |
| 2026-08-22 | 12px legibility floor as `fontSize.label` | 139 inline `text-[10px]`/`[11px]` literals across 14 components were below the floor. Naming it makes the floor one decision rather than 139. |
| 2026-08-22 | Removed Inter + JetBrains Mono | Both were still loading from the old system on every page; JetBrains Mono was referenced nowhere, Inter only by the chart. `body` also carried `text-gray-200`, which beat `var(--on-ink)` on specificity and made the app's default text cool grey rather than warm bone. |
