import { describe, expect, it } from "vitest";

import type { Bar } from "../api/client";
import { change, closeDaysAgo, positionIn, previousClose, rangeOver, sparklinePath } from "./stats";

const DAY = 86_400_000;
const NOW = Date.parse("2026-10-05T12:00:00Z");

function daily(daysAgo: number, close: number, low = close - 1, high = close + 1): Bar {
  const ts = new Date(Date.parse("2026-10-05T00:00:00Z") - daysAgo * DAY).toISOString();
  return { ts, open: close, high, low, close, volume: 1, is_quote_only: false, is_outlier: false };
}

// Oldest first, as the API returns them.
const BARS = [daily(40, 80), daily(30, 90), daily(8, 95), daily(7, 100), daily(1, 110, 104, 112)];

describe("price statistics", () => {
  it("measures change as a fraction", () => {
    expect(change(100, 110)).toBeCloseTo(0.1);
    expect(change(undefined, 110)).toBeUndefined();
    expect(change(0, 110)).toBeUndefined();
  });

  it("finds the close a number of days back without looking ahead", () => {
    expect(closeDaysAgo(BARS, 7, NOW)).toBe(100);
    expect(closeDaysAgo(BARS, 30, NOW)).toBe(90);
    expect(closeDaysAgo(BARS, 365, NOW)).toBeUndefined();
    expect(previousClose(BARS)).toBe(110);
    expect(previousClose([])).toBeUndefined();
  });

  it("finds the range over a window and includes the latest price", () => {
    expect(rangeOver(BARS, 10, NOW)).toEqual({ low: 94, high: 112 });
    expect(rangeOver(BARS, 10, NOW, 120)).toEqual({ low: 94, high: 120 });
    expect(rangeOver([], 10, NOW)).toBeUndefined();
    // A bad print: the low of a flagged bar is ignored in favour of its close.
    const suspect = { ...daily(2, 108, 10, 109), is_outlier: true };
    expect(rangeOver([...BARS, suspect], 10, NOW)).toEqual({ low: 94, high: 112 });
  });

  it("places a price inside a range", () => {
    expect(positionIn({ low: 100, high: 200 }, 150)).toBe(0.5);
    expect(positionIn({ low: 100, high: 200 }, 250)).toBe(1);
    expect(positionIn({ low: 100, high: 100 }, 100)).toBe(0.5);
  });

  it("draws a sparkline path inside its box", () => {
    expect(sparklinePath([1, 2, 3], 100, 20, 0)).toBe("M0.0 20.0 L50.0 10.0 L100.0 0.0");
    expect(sparklinePath([5], 100, 20)).toBe("");
  });
});
