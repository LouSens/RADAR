// Pure geometry and wording for the Outlook panel.

import type { CalibrationRow, OutlookHorizon, OutlookRange } from "../api/client";

export interface HistogramBar {
  x: number;
  width: number;
  y: number;
  height: number;
  from: number;
  to: number;
}

/** Bars for a histogram drawn in a `width` by `height` box, tallest bar touching the top. */
export function histogramBars(
  horizon: OutlookHorizon,
  width: number,
  height: number,
): HistogramBar[] {
  const edges = horizon.histogram_edges;
  const counts = horizon.histogram_counts;
  const first = edges[0];
  const last = edges.at(-1);
  const tallest = Math.max(...counts, 1);
  if (first === undefined || last === undefined || last <= first) return [];
  const scale = width / (last - first);
  return counts.map((count, i) => {
    const from = edges[i] ?? first;
    const to = edges[i + 1] ?? last;
    const barHeight = (count / tallest) * height;
    return {
      x: (from - first) * scale,
      width: Math.max((to - from) * scale - 1, 0.5),
      y: height - barHeight,
      height: barHeight,
      from,
      to,
    };
  });
}

/** Where a price sits across the histogram, from 0 to 1, or undefined if outside it. */
export function positionInHistogram(horizon: OutlookHorizon, price: number): number | undefined {
  const first = horizon.histogram_edges[0];
  const last = horizon.histogram_edges.at(-1);
  if (first === undefined || last === undefined || last <= first) return undefined;
  const at = (price - first) / (last - first);
  return at < 0 || at > 1 ? undefined : at;
}

/** The range to show: adjusted by past accuracy where that has been measured. */
export function shownRange(range: OutlookRange): {
  low: number;
  high: number;
  adjusted: boolean;
} {
  if (range.adjusted_low != null && range.adjusted_high != null) {
    return {
      low: range.adjusted_low,
      high: range.adjusted_high,
      adjusted: true,
    };
  }
  return { low: range.low, high: range.high, adjusted: false };
}

export interface FanShape {
  outer: string;
  inner: string;
  median: string;
  low: number;
  high: number;
}

/** Fan chart paths for the first `steps` steps: 5 to 95% band, 25 to 75% band, and the median. */
export function fanShape(
  fan: Record<string, number[]>,
  steps: number,
  width: number,
  height: number,
): FanShape | undefined {
  const take = (key: string) => (fan[key] ?? []).slice(0, steps + 1);
  const q05 = take("0.05");
  const q25 = take("0.25");
  const q50 = take("0.5");
  const q75 = take("0.75");
  const q95 = take("0.95");
  if (q50.length < 2 || [q05, q25, q75, q95].some((q) => q.length !== q50.length)) {
    return undefined;
  }
  const low = Math.min(...q05);
  const high = Math.max(...q95);
  const span = high - low || 1;
  const x = (i: number) => (i / (q50.length - 1)) * width;
  const y = (value: number) => height - ((value - low) / span) * height;
  const point = (v: number, i: number) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`;
  const line = (values: number[]) =>
    values.map((v, i) => `${i === 0 ? "M" : "L"}${point(v, i)}`).join(" ");
  const band = (lower: number[], upper: number[]) =>
    `${line(upper)} ${lower
      .map((v, i) => `L${point(v, i)}`)
      .reverse()
      .join(" ")} Z`;
  return {
    outer: band(q05, q95),
    inner: band(q25, q75),
    median: line(q50),
    low,
    high,
  };
}

/** "7 days" for crypto, "5 market sessions" for stocks. */
export function stepsLabel(steps: number, continuous: boolean): string {
  const unit = continuous ? "day" : "market session";
  return `${steps} ${unit}${steps === 1 ? "" : "s"}`;
}

/**
 * Forecast error of the simulator against a constant-volatility random walk, as a
 * fraction: negative means the simulator had the smaller error.
 */
export function errorAgainstBaseline(row: CalibrationRow): number {
  return row.pinball_model / row.pinball_baseline - 1;
}
