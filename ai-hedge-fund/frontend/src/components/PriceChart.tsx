import { useEffect, useMemo, useRef } from "react";
import { createChart, type IChartApi, ColorType } from "lightweight-charts";

interface Props {
  data: Record<string, unknown>[];
  /** Distinguishes "still fetching" from "fetched, and there is nothing".
   *  Without it an empty result reads as a load that never finishes. */
  loading?: boolean;
}

export function PriceChart({ data, loading = false }: Props) {
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
    const token = (name: string) => root.getPropertyValue(name).trim();

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: token("--on-ink-faint"),
        fontFamily: '"Departure Mono", ui-monospace, monospace',
      },
      grid: {
        vertLines: { color: token("--ink-line") },
        horzLines: { color: token("--ink-line") },
      },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
      crosshair: {
        vertLine: { color: token("--cobalt"), width: 1, style: 2 },
        horzLine: { color: token("--cobalt"), width: 1, style: 2 },
      },
      rightPriceScale: {
        borderColor: token("--ink-line"),
      },
      timeScale: {
        borderColor: token("--ink-line"),
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
  }, [chartData]);

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
