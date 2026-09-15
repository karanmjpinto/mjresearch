import { useEffect, useMemo, useRef } from "react";
import { useTheme } from "@/lib/theme";
import { createChart, type IChartApi, ColorType } from "lightweight-charts";

interface Props {
  data: Record<string, unknown>[];
  /** Distinguishes "still fetching" from "fetched, and there is nothing".
   *  Without it an empty result reads as a load that never finishes. */
  loading?: boolean;
}

/**
 * Resolve a palette token to a colour lightweight-charts can actually parse.
 *
 * The palette is authored in `oklch()`, and the charting library does its own
 * colour parsing rather than the browser's — it throws on any modern colour
 * space, which takes the whole surrounding view down with it. `color-mix` in
 * sRGB forces the engine to hand back plain channels, which is the browser
 * doing the conversion correctly rather than us reimplementing OKLCH here.
 *
 * Anything already in a legacy notation is passed straight through, so this
 * costs nothing once the palette stops using oklch.
 */
function toChartColor(value: string): string {
  let v = (value || "").trim();
  if (!v) return "";
  if (/^#|^rgb|^hsl/i.test(v)) return v;

  /* Since the palette gained a second theme, the custom properties hold OKLCH
   * *channels* — `19% 0.012 60` — rather than a finished colour, so that one
   * token name can mean the right thing in daylight and at night. A bare
   * triplet is not a colour to any parser, which is what took this chart and
   * its whole view down: the library throws "Cannot parse color" and the error
   * boundary swallows the page. Wrap it back up before converting. */
  if (!/^[a-z]/i.test(v)) v = `oklch(${v})`;

  const probe = document.createElement("span");
  probe.style.color = `color-mix(in srgb, ${v} 100%, transparent)`;
  document.body.appendChild(probe);
  const resolved = getComputedStyle(probe).color;
  probe.remove();

  const nums = resolved.match(/-?[\d.]+(?:e-?\d+)?/g);
  if (!nums || nums.length < 3) return v;
  // `color(srgb ...)` reports 0–1 channels; `rgb(...)` reports 0–255.
  const isFraction = /^color\(/i.test(resolved);
  const to255 = (n: string) =>
    Math.max(
      0,
      Math.min(
        255,
        Math.round(isFraction ? parseFloat(n) * 255 : parseFloat(n)),
      ),
    );
  const [r, g, b] = [to255(nums[0]!), to255(nums[1]!), to255(nums[2]!)];
  const a = nums.length > 3 ? parseFloat(nums[3]!) : 1;
  return a >= 1 ? `rgb(${r}, ${g}, ${b})` : `rgba(${r}, ${g}, ${b}, ${a})`;
}

export function PriceChart({ data, loading = false }: Props) {
  // The canvas cannot inherit a CSS variable, so the chart is rebuilt when the
  // theme changes rather than restyled.
  const { resolved: theme } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  // Derived here rather than inside the effect so the empty state and the
  // aria-label count the candles actually drawn, not the raw rows handed in —
  // the filter below can discard records with missing OHLC.
  const chartData = useMemo(
    () =>
      data
        .filter((d) => d.date && d.open && d.high && d.low && d.close)
        .map((d) => ({
          time: String(d.date).split("T")[0].split(" ")[0],
          open: Number(d.open),
          high: Number(d.high),
          low: Number(d.low),
          close: Number(d.close),
        }))
        .sort((a, b) => a.time.localeCompare(b.time)),
    [data],
  );

  useEffect(() => {
    if (!containerRef.current) return;

    // The chart paints to canvas, so it cannot take `var(--token)` the way the
    // rest of the UI does — it needs resolved values. Read them off :root at
    // mount instead of hardcoding hex, so the chart moves with the palette.
    const root = getComputedStyle(document.documentElement);
    const token = (name: string) =>
      toChartColor(root.getPropertyValue(name).trim());

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: token("--on-ground-faint"),
        fontFamily: '"Departure Mono", ui-monospace, monospace',
      },
      grid: {
        vertLines: { color: token("--ground-line") },
        horzLines: { color: token("--ground-line") },
      },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
      crosshair: {
        vertLine: { color: token("--cobalt"), width: 1, style: 2 },
        horzLine: { color: token("--cobalt"), width: 1, style: 2 },
      },
      rightPriceScale: {
        borderColor: token("--ground-line"),
      },
      timeScale: {
        borderColor: token("--ground-line"),
      },
    });

    const series = chart.addCandlestickSeries({
      upColor: token("--verdigris"),
      downColor: token("--oxide"),
      wickUpColor: token("--verdigris"),
      wickDownColor: token("--oxide"),
      borderVisible: false,
    });

    if (chartData.length > 0) {
      series.setData(chartData as Parameters<typeof series.setData>[0]);
      chart.timeScale().fitContent();
    }

    chartRef.current = chart;

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, [chartData, theme]);

  if (chartData.length === 0) {
    return (
      <div className="w-full h-full flex items-center justify-center text-on-ink-faint text-sm">
        {loading ? "Loading chart data…" : "No price data for this range."}
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="w-full h-full"
      role="img"
      aria-label={`Price candlestick chart, ${chartData.length} sessions`}
    />
  );
}
