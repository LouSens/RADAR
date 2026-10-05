import {
  AreaSeries,
  CandlestickSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { Bar, Timeframe } from "../api/client";
import type { LivePrice } from "../api/live";
import { chartSeconds, tradingDay } from "../lib/time";

type Kind = "area" | "candles";
type AssetClass = "crypto" | "stock";

interface Props {
  bars: Bar[];
  timeframe: Timeframe;
  assetClass: AssetClass;
  kind: Kind;
  /** CSS variable holding the series colour, for example "--btc". */
  colorVar: string;
  /** A fresh live price, or undefined when there is none. */
  live?: LivePrice;
  /** Pixels, or "100%" to fill a sized parent. */
  height?: number | string;
  label: string;
}

const HOUR_MS = 3_600_000;

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Where a bar sits on the time axis: local clock time for hours, the trading day for days. */
function axisTime(ts: string, timeframe: Timeframe, assetClass: AssetClass): Time {
  return timeframe === "1Day"
    ? tradingDay(ts, assetClass)
    : (chartSeconds(ts) as UTCTimestamp);
}

function themeOptions() {
  return {
    layout: {
      background: { color: "transparent" },
      textColor: cssVar("--muted"),
      fontFamily: cssVar("--font-mono") || "monospace",
      attributionLogo: false,
    },
    grid: {
      vertLines: { color: cssVar("--grid") },
      horzLines: { color: cssVar("--grid") },
    },
    crosshair: {
      vertLine: { color: cssVar("--line-strong"), labelBackgroundColor: "#1a1c25" },
      horzLine: { color: cssVar("--line-strong"), labelBackgroundColor: "#1a1c25" },
    },
    rightPriceScale: { borderColor: cssVar("--line") },
    timeScale: { borderColor: cssVar("--line"), timeVisible: true, secondsVisible: false },
  };
}

export function PriceChart({
  bars,
  timeframe,
  assetClass,
  kind,
  colorVar,
  live,
  height = 260,
  label,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Area"> | ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!container.current) return;
    const created = createChart(container.current, { autoSize: true, ...themeOptions() });
    const color = cssVar(colorVar);
    series.current =
      kind === "candles"
        ? created.addSeries(CandlestickSeries, {
            upColor: cssVar("--calm"),
            downColor: cssVar("--alert"),
            wickUpColor: cssVar("--calm"),
            wickDownColor: cssVar("--alert"),
            borderVisible: false,
          })
        : created.addSeries(AreaSeries, {
            lineColor: color,
            topColor: `color-mix(in srgb, ${color} 30%, transparent)`,
            bottomColor: `color-mix(in srgb, ${color} 0%, transparent)`,
            priceLineColor: color,
            lineWidth: 2,
          });
    chart.current = created;

    const scheme = window.matchMedia("(prefers-color-scheme: dark)");
    const retheme = () => created.applyOptions(themeOptions());
    scheme.addEventListener("change", retheme);
    return () => {
      scheme.removeEventListener("change", retheme);
      created.remove();
      chart.current = null;
      series.current = null;
    };
  }, [kind, colorVar]);

  useEffect(() => {
    const target = series.current;
    if (!target) return;
    if (kind === "candles") {
      (target as ISeriesApi<"Candlestick">).setData(
        bars.map((b) => ({
          time: axisTime(b.ts, timeframe, assetClass),
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
        })),
      );
    } else {
      (target as ISeriesApi<"Area">).setData(
        bars.map((b) => ({ time: axisTime(b.ts, timeframe, assetClass), value: b.close })),
      );
    }
    chart.current?.timeScale().fitContent();
  }, [bars, timeframe, assetClass, kind]);

  // Draw the bar that is still forming from the live price. It is never stored.
  useEffect(() => {
    const target = series.current;
    const last = bars.at(-1);
    if (!target || !live || !last) return;
    const liveMs = Date.parse(live.ts);
    const bucket =
      timeframe === "1Day"
        ? new Date(liveMs).toISOString()
        : new Date(Math.floor(liveMs / HOUR_MS) * HOUR_MS).toISOString();
    if (Date.parse(bucket) < Date.parse(last.ts) && timeframe === "1Hour") return;
    const time = axisTime(bucket, timeframe, assetClass);
    const sameBar = time === axisTime(last.ts, timeframe, assetClass);
    if (kind === "candles") {
      const open = sameBar ? last.open : last.close;
      (target as ISeriesApi<"Candlestick">).update({
        time,
        open,
        high: Math.max(sameBar ? last.high : open, live.price),
        low: Math.min(sameBar ? last.low : open, live.price),
        close: live.price,
      });
    } else {
      (target as ISeriesApi<"Area">).update({ time, value: live.price });
    }
  }, [live, bars, timeframe, assetClass, kind]);

  return <div ref={container} role="img" aria-label={label} style={{ height }} />;
}
