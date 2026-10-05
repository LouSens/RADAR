import { describe, expect, it } from "vitest";

import type { CalibrationRow, OutlookHorizon } from "../api/client";
import {
  errorAgainstBaseline,
  fanShape,
  histogramBars,
  positionInHistogram,
  shownRange,
  stepsLabel,
} from "./outlook";

const HORIZON: OutlookHorizon = {
  horizon_days: 7,
  steps: 7,
  quantiles: { "0.5": 100 },
  intervals: [],
  histogram_edges: [90, 100, 110, 120],
  histogram_counts: [10, 40, 20],
  expected_worst_drawdown: -0.04,
  mean_return: 0.01,
};

describe("outlook geometry", () => {
  it("scales histogram bars to the box", () => {
    const bars = histogramBars(HORIZON, 300, 100);
    expect(bars).toHaveLength(3);
    expect(bars[1]).toMatchObject({
      x: 100,
      y: 0,
      height: 100,
      from: 100,
      to: 110,
    });
    expect(bars[0]?.height).toBe(25);
    expect(bars[2]?.x).toBe(200);
  });

  it("places a price across the histogram, or nowhere when outside it", () => {
    expect(positionInHistogram(HORIZON, 105)).toBe(0.5);
    expect(positionInHistogram(HORIZON, 130)).toBeUndefined();
  });

  it("shows the adjusted range when there is one", () => {
    const raw = { level: 0.8, low: 95, high: 106, adjusted_is_widest: false };
    expect(shownRange({ ...raw, adjusted_low: 94, adjusted_high: 107 })).toEqual({
      low: 94,
      high: 107,
      adjusted: true,
    });
    expect(shownRange({ ...raw, adjusted_low: null, adjusted_high: null })).toEqual({
      low: 95,
      high: 106,
      adjusted: false,
    });
  });

  it("draws a fan that starts at one point and covers only the chosen steps", () => {
    const fan = {
      "0.05": [100, 96, 93, 90],
      "0.25": [100, 98, 97, 96],
      "0.5": [100, 100, 101, 101],
      "0.75": [100, 102, 104, 105],
      "0.95": [100, 105, 108, 112],
    };
    const shape = fanShape(fan, 2, 200, 100);
    expect(shape?.low).toBe(93);
    expect(shape?.high).toBe(108);
    expect(shape?.median.startsWith("M0.0,")).toBe(true);
    expect(shape?.median.split("L")).toHaveLength(3);
    expect(fanShape({}, 2, 200, 100)).toBeUndefined();
  });

  it("names steps by how the market trades", () => {
    expect(stepsLabel(7, true)).toBe("7 days");
    expect(stepsLabel(5, false)).toBe("5 market sessions");
    expect(stepsLabel(1, false)).toBe("1 market session");
  });

  it("compares forecast error with the baseline", () => {
    const row = {
      pinball_model: 0.0097,
      pinball_baseline: 0.0094,
    } as CalibrationRow;
    expect(errorAgainstBaseline(row)).toBeCloseTo(0.0319, 3);
  });
});
