/**
 * The shared scale behind the football field.
 *
 * Every bar and the price marker are placed on one scale, because the whole
 * point of the chart is comparing methods to each other and to what you would
 * pay today. Per-row autoscaling would make disagreement invisible.
 *
 * The price is folded into the extent rather than overlaid on top of it, which
 * is what guarantees the marker lands inside the drawing even when the price
 * sits far outside every band — Apple at 332 against bands topping out at 226
 * being exactly that case.
 */

export type Extent = { min: number; span: number };

/** Points that must be visible: every band edge, plus the price. */
export function compsExtent(points: number[], pad = 0.06): Extent {
  const usable = points.filter((n) => Number.isFinite(n) && n > 0);
  if (usable.length === 0) return { min: 0, span: 1 };

  const lo = Math.min(...usable);
  const hi = Math.max(...usable);
  // A single point, or a set with no width, still needs a non-zero span or
  // every position becomes a division by zero.
  const padding = (hi - lo) * pad || Math.max(lo * pad, 1);
  const min = lo - padding;
  return { min, span: hi + padding - min };
}

/** Position of a value on the extent, as a percentage. */
export function compsPct(value: number, { min, span }: Extent): number {
  if (!Number.isFinite(value) || span <= 0) return 0;
  return ((value - min) / span) * 100;
}
