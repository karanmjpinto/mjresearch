import { useEffect, useRef } from "react";
import { createChart, type IChartApi, ColorType } from "lightweight-charts";

interface Props {
  data: Record<string, unknown>[];
}

export function PriceChart({ data }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#9CA3AF",
        fontFamily: "Inter, system-ui, sans-serif",
      },
      grid: {
        vertLines: { color: "#1E2736" },
        horzLines: { color: "#1E2736" },
      },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
      crosshair: {
        vertLine: { color: "#3B82F6", width: 1, style: 2 },
        horzLine: { color: "#3B82F6", width: 1, style: 2 },
      },
      rightPriceScale: {
        borderColor: "#1E2736",
      },
      timeScale: {
        borderColor: "#1E2736",
      },
    });

    const series = chart.addCandlestickSeries({
      upColor: "#10B981",
      downColor: "#EF4444",
      wickUpColor: "#10B981",
      wickDownColor: "#EF4444",
      borderVisible: false,
    });

    // Transform data for lightweight-charts
    const chartData = data
      .filter((d) => d.date && d.open && d.high && d.low && d.close)
      .map((d) => ({
        time: String(d.date).split("T")[0].split(" ")[0],
        open: Number(d.open),
        high: Number(d.high),
        low: Number(d.low),
        close: Number(d.close),
      }))
      .sort((a, b) => a.time.localeCompare(b.time));

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
  }, [data]);

  if (data.length === 0) {
    return (
      <div className="w-full h-full flex items-center justify-center text-gray-600 text-sm">
        Loading chart data...
      </div>
    );
  }

  return <div ref={containerRef} className="w-full h-full" />;
}
