// Small, pure calculations for the figures shown beside prices. Every one uses only bars
// at or before the moment it describes.

import type { Bar } from "../api/client";

const DAY_MS = 86_400_000;

/** Fractional change from `from` to `to`, or undefined if either is missing. */
export function change(from: number | undefined, to: number | undefined): number | undefined {
  if (from === undefined || to === undefined || from === 0) return undefined;
  return to / from - 1;
}

/** Close of the latest daily bar that started at least `days` before `now`. */
export function closeDaysAgo(daily: Bar[], days: number, now: number): number | undefined {
  const cutoff = now - days * DAY_MS;
  for (let i = daily.length - 1; i >= 0; i--) {
    const bar = daily[i];
    if (bar && Date.parse(bar.ts) <= cutoff) return bar.close;
  }
  return undefined;
}

/** The latest completed daily close: the reference for "since previous close". */
export function previousClose(daily: Bar[]): number | undefined {
  return daily.at(-1)?.close;
}

export interface Range {
  low: number;
  high: number;
}

/** Lowest low and highest high over the last `days`, widened to include `latest`. */
export function rangeOver(
  daily: Bar[],
  days: number,
  now: number,
  latest?: number,
): Range | undefined {
  const cutoff = now - days * DAY_MS;
  const recent = daily.filter((bar) => Date.parse(bar.ts) >= cutoff);
  if (recent.length === 0) return undefined;
  // A bar flagged as suspect contributes its close only: its high or low may be a bad print.
  let low = Math.min(...recent.map((bar) => (bar.is_outlier ? bar.close : bar.low)));
  let high = Math.max(...recent.map((bar) => (bar.is_outlier ? bar.close : bar.high)));
  if (latest !== undefined) {
    low = Math.min(low, latest);
    high = Math.max(high, latest);
  }
  return { low, high };
}

/** Where a price sits inside a range, from 0 (at the low) to 1 (at the high). */
export function positionIn(range: Range, price: number): number {
  if (range.high === range.low) return 0.5;
  return Math.min(1, Math.max(0, (price - range.low) / (range.high - range.low)));
}

/** Points for an SVG sparkline, scaled into a box. */
export function sparklinePath(values: number[], width: number, height: number, pad = 2): string {
  if (values.length < 2) return "";
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  return values
    .map((value, i) => {
      const x = pad + (i / (values.length - 1)) * (width - 2 * pad);
      const y = height - pad - ((value - low) / span) * (height - 2 * pad);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}
