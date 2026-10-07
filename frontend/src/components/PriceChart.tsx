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
  return timeframe === "1Day" ? tradingDay(ts, assetClass) : (chartSeconds(ts) as UTCTimestamp);
}

/** Whole numbers for large prices, so the scale stays narrow on a phone. */
function axisPrice(price: number): string {
  return Math.abs(price) >= 1000 ? Math.round(price).toLocaleString("en-US") : price.toFixed(2);
}

function themeOptions(timeframe: Timeframe) {
  return {
    localization: { priceFormatter: axisPrice },
    // The page scrolls past the chart: the wheel and an up-or-down swipe belong to the page.
    // Dragging sideways moves through time, a pinch or a drag on the time axis zooms.
    handleScroll: {
      mouseWheel: false,
      pressedMouseMove: true,
      horzTouchDrag: true,
      vertTouchDrag: false,
    },
    handleScale: {
      mouseWheel: false,
      pinch: true,
      axisPressedMouseMove: { time: true, price: false },
      axisDoubleClickReset: { time: true, price: true },
    },
    layout: {
      background: { color: "transparent" },
      textColor: cssVar("--muted"),
      fontFamily: "Inter, system-ui, sans-serif",
      fontSize: 11,
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
    timeScale: {
      borderColor: cssVar("--line"),
      timeVisible: timeframe === "1Hour",
      secondsVisible: false,
      // Never show time with no prices: the view stops at the first and last bar, and
      // bars may shrink as far as needed for the whole period to fit a narrow screen.
      fixLeftEdge: true,
      fixRightEdge: true,
      minBarSpacing: 0.01,
      rightOffset: 0,
    },
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
    const host = container.current;
    const created = createChart(host, { autoSize: true, ...themeOptions(timeframe) });
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
    const retheme = () => created.applyOptions(themeOptions(timeframe));
    scheme.addEventListener("change", retheme);

    // When the space changes (a resized window, a rotated phone, the sidebar folding),
    // fit the whole period to the new width again.
    let width = host.clientWidth;
    let frame = 0;
    const resized =
      typeof ResizeObserver === "undefined"
        ? undefined
        : new ResizeObserver(() => {
            if (host.clientWidth === width) return;
            width = host.clientWidth;
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(() => created.timeScale().fitContent());
          });
    resized?.observe(host);
    return () => {
      resized?.disconnect();
      cancelAnimationFrame(frame);
      scheme.removeEventListener("change", retheme);
      created.remove();
      chart.current = null;
      series.current = null;
    };
  }, [kind, colorVar, timeframe]);

  useEffect(() => {
    const target = series.current;
    if (!target) return;
    if (kind === "candles") {
      (target as ISeriesApi<"Candlestick">).setData(
        bars.map((b) => ({
          time: axisTime(b.ts, timeframe, assetClass),
          open: b.open,
          // A bar flagged as suspect is drawn without wicks: its high or low may be a bad print.
          high: b.is_outlier ? Math.max(b.open, b.close) : b.high,
          low: b.is_outlier ? Math.min(b.open, b.close) : b.low,
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
