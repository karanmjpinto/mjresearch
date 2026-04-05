# Design System — MJ Research (AI Hedge Fund)

## Product Context

- **What this is:** A local-first financial research and portfolio desk: market data, fundamentals, technicals, AI-assisted thesis (Ollama), and a SQLite-backed portfolio with risk.
- **Who it's for:** You and power users who live in tickers, tables, and charts — not casual retail onboarding flows.
- **Space/industry:** Fintech / research terminal (peers: Koyfin-style density, Bloomberg-adjacent seriousness without the terminal chrome).
- **Project type:** Dark-mode web app (dashboard + research + portfolio).

## Aesthetic Direction

- **Direction:** Industrial / utilitarian — data-first, low ornament, confidence from clarity.
- **Decoration level:** Minimal — texture only where it aids scan (subtle borders, card lift).
- **Mood:** Calm, precise, institutional — “tool for decisions,” not marketing fluff.
- **Reference sites:** (optional) Dense research UIs; category baseline is dark + monospace numerals + restrained accent.

## Typography

- **Display/Hero:** DM Sans (600–700) — modern, neutral, readable at large sizes without feeling “startup template.”
- **Body:** DM Sans (400–500) — pairs with display; single family keeps the UI quiet.
- **UI/Labels:** Same as body; use weight + size for hierarchy.
- **Data/Tables:** JetBrains Mono with `tabular-nums` — aligns decimals; non-negotiable for holdings and prices.
- **Code:** JetBrains Mono.
- **Loading:** Google Fonts (`https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap`).
- **Scale:** xs 12px / sm 14px / base 16px / lg 18px / xl 22px / 2xl 28px / 3xl 36px (use rem in app).

## Color

- **Approach:** Restrained — color encodes *meaning* (P&L, risk, primary action), not decoration.
- **Primary:** `#3b82f6` — links, active nav, primary buttons (research “focus”).
- **Secondary:** `#64748b` — secondary labels, disabled-adjacent text.
- **Neutrals (dark):** Background `#0a0a0b`, elevated `#121214`, border `#27272a`, text primary `#fafafa`, text muted `#a1a1aa`.
- **Semantic:** success `#22c55e`, warning `#f59e0b`, error `#ef4444`, info `#38bdf8`.
- **Dark mode:** Default; reduce saturation ~10% on large fills vs. pure primaries to avoid glow on OLED.

## Spacing

- **Base unit:** 4px.
- **Density:** Compact — this is a desk, not a landing page; prioritize rows visible without crowding touch targets.
- **Scale:** 2xs 2 / xs 4 / sm 8 / md 16 / lg 24 / xl 32 / 2xl 48 / 3xl 64.

## Layout

- **Approach:** Hybrid — grid-disciplined for portfolio tables and research metrics; single-column reading width for long thesis text when AI is on.
- **Grid:** 12 columns at `lg`; collapse to single column on small screens with sticky subnav where needed.
- **Max content width:** 1280px for main desk; full bleed only for charts when useful.
- **Border radius:** sm 6px (inputs, small chips), md 10px (cards), lg 14px (modals), full for pills.

## Motion

- **Approach:** Minimal-functional — short fades for tab switches; no gratuitous motion on numbers.
- **Easing:** enter `ease-out`, exit `ease-in`, move `ease-in-out`.
- **Duration:** micro 75ms / short 150ms / medium 250ms / long 400ms.

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-30 | Initial design system | `/design-consultation` aligned to existing MJ Research dark desk + fintech conventions |
| 2026-03-30 | Single accent (blue) | Avoid purple-gradient “AI product” cliché; risks live in typography + data density instead |
