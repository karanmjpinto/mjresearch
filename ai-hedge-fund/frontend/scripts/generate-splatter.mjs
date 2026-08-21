/**
 * Generates the drip field used behind the landing page.
 *
 * Pollock worked by flinging liquid enamel from a stick held above the canvas,
 * so the marks are not random dots — each throw is an arc, and the paint that
 * leaves the stick lands as a thinning trail of decreasing blobs with satellite
 * spatter where it hit hardest. This models that: pick an arc, walk along it
 * losing paint, and drop the occasional satellite.
 *
 * Seeded so the artwork is committed rather than re-rolled on every build.
 * Change SEED to draw a different canvas.
 *
 *   node scripts/generate-splatter.mjs > public/splatter.svg
 */

const SEED = 20260821;
const W = 1600;
const H = 1200;

// Colours must match the tokens in src/index.css.
const THROWS = [
  { color: "#1F1B17", weight: 26, opacity: 0.92 }, // enamel black, the armature
  { color: "#8C3A22", weight: 18, opacity: 0.88 }, // oxide red
  { color: "#D9A441", weight: 16, opacity: 0.85 }, // cadmium yellow
  { color: "#2F4B8F", weight: 13, opacity: 0.85 }, // cobalt
  { color: "#5E8C7F", weight: 8, opacity: 0.75 },  // verdigris
  { color: "#B9B2A4", weight: 11, opacity: 0.7 },  // aluminium
];

/** mulberry32 — small, fast, and reproducible across machines. */
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rand = rng(SEED);
const between = (lo, hi) => lo + rand() * (hi - lo);

/** One throw: a quadratic arc walked from start to end, shedding paint. */
function throwPaint({ color, opacity }) {
  const x0 = between(-0.1 * W, 1.1 * W);
  const y0 = between(-0.1 * H, 1.1 * H);
  const angle = between(0, Math.PI * 2);
  const length = between(0.25 * W, 0.85 * W);
  const x1 = x0 + Math.cos(angle) * length;
  const y1 = y0 + Math.sin(angle) * length;
  // Control point offset perpendicular to the throw gives the arc its whip.
  const cx = (x0 + x1) / 2 + Math.cos(angle + Math.PI / 2) * between(-260, 260);
  const cy = (y0 + y1) / 2 + Math.sin(angle + Math.PI / 2) * between(-260, 260);

  const parts = [];
  const strokeW = between(1.2, 4.5);
  parts.push(
    `<path d="M${x0.toFixed(0)} ${y0.toFixed(0)} Q${cx.toFixed(0)} ${cy.toFixed(0)} ${x1.toFixed(0)} ${y1.toFixed(0)}" ` +
      `fill="none" stroke="${color}" stroke-width="${strokeW.toFixed(1)}" ` +
      `stroke-linecap="round" opacity="${(opacity * between(0.5, 0.9)).toFixed(1)}"/>`
  );

  // Paint sheds along the arc, heaviest at the start of the throw.
  const drops = Math.round(between(26, 60));
  for (let i = 0; i < drops; i++) {
    const t = i / drops;
    const mt = 1 - t;
    const px = mt * mt * x0 + 2 * mt * t * cx + t * t * x1;
    const py = mt * mt * y0 + 2 * mt * t * cy + t * t * y1;
    const falloff = 1 - t * between(0.5, 0.95);
    const r = Math.max(0.6, between(1.2, 7.5) * falloff);
    const jitter = between(-9, 9);
    parts.push(
      `<ellipse cx="${(px + jitter).toFixed(0)}" cy="${(py + jitter).toFixed(0)}" ` +
        `rx="${r.toFixed(1)}" ry="${(r * between(0.6, 1.5)).toFixed(1)}" ` +
        `fill="${color}" opacity="${(opacity * between(0.4, 1)).toFixed(1)}"/>`
    );

    // Where a drop lands hard it throws satellites.
    if (rand() < 0.34) {
      const n = Math.round(between(3, 9));
      for (let s = 0; s < n; s++) {
        const sr = Math.max(0.4, r * between(0.1, 0.35));
        parts.push(
          `<circle cx="${(px + between(-34, 34)).toFixed(0)}" cy="${(py + between(-34, 34)).toFixed(0)}" ` +
            `r="${sr.toFixed(1)}" fill="${color}" opacity="${(opacity * between(0.25, 0.7)).toFixed(1)}"/>`
        );
      }
    }
  }
  return parts.join("");
}

// Build a shuffled work list so colours interleave rather than stacking as
// discrete layers. Pollock's canvases weave — black over red over black again.
const worklist = [];
for (const spec of THROWS) {
  for (let i = 0; i < spec.weight; i++) worklist.push(spec);
}
for (let i = worklist.length - 1; i > 0; i--) {
  const j = Math.floor(rand() * (i + 1));
  [worklist[i], worklist[j]] = [worklist[j], worklist[i]];
}
const layers = worklist.map(throwPaint);

process.stdout.write(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="presentation">` +
    `<g shape-rendering="geometricPrecision">${layers.join("")}</g>` +
    `</svg>\n`
);
