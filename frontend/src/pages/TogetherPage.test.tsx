import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Drivers, Relationships } from "../api/client";
import { driverHeadline } from "../components/DriversPanel";
import { correlationPath, linkWords, spillSentence, weekendSentence } from "../lib/together";
import { TogetherPage } from "./TogetherPage";

const state = vi.hoisted(() => ({ data: undefined as unknown }));

vi.mock("../api/queries", () => ({
  useRelationships: () => ({ data: state.data, isPending: false }),
  useAssets: () => ({
    data: [
      { symbol: "BTC/USD", name: "Bitcoin" },
      { symbol: "GLD", name: "Gold" },
      { symbol: "SPY", name: "US stocks (S&P 500)" },
    ],
  }),
}));

const solid = { grade: "solid" as const, reason: "Measured on 1,443 trading days." };
const spill = (source: string, target: string, steps: number, ratio: number | null) => ({
  source,
  target,
  steps,
  episodes: ratio == null ? 9 : 16,
  after: ratio == null ? null : 0.012,
  usual: ratio == null ? null : 0.008,
  ratio,
  ratio_low: ratio == null ? null : ratio - 0.4,
  ratio_high: ratio == null ? null : ratio + 0.5,
  p_value: ratio == null ? null : 0.01,
  p_adjusted: ratio == null ? null : ratio > 1.5 ? 0.03 : 0.3,
  verdict:
    ratio == null
      ? ("not enough episodes" as const)
      : ratio > 1.5
        ? ("spills over" as const)
        : ("no measurable spillover" as const),
});

const DATA: Relationships = {
  as_of: "2026-10-02T20:00:00Z",
  pairs: [
    {
      a: "BTC/USD",
      b: "GLD",
      current_30: 0.5,
      current_90: 0.53,
      current_weighted: 0.45,
      low_90: 0.36,
      high_90: 0.67,
      full: 0.11,
      n_days: 1443,
      first_day: "2021-01-05",
      last_day: "2026-10-02",
      series: [
        { day: "2026-09-30", rolling_30: 0.4, rolling_90: 0.5, weighted: 0.42 },
        { day: "2026-10-01", rolling_30: 0.5, rolling_90: 0.53, weighted: 0.45 },
      ],
      regime_of: "BTC/USD",
      by_regime: [
        { label: "calm", n: 512, correlation: 0.08, low: -0.01, high: 0.16 },
        { label: "turbulent", n: 12, correlation: null, low: null, high: null },
      ],
      trust: solid,
    },
  ],
  grid_recent: {
    symbols: ["GLD", "BTC/USD"],
    matrix: [
      [1, 0.53],
      [0.53, 1],
    ],
    n_days: 90,
    first_day: "2026-05-27",
    last_day: "2026-10-02",
  },
  grid_full: null,
  spillovers: [
    spill("GLD", "SPY", 5, 1.64),
    spill("GLD", "SPY", 1, 2.05),
    spill("BTC/USD", "GLD", 5, 1.1),
    spill("GLD", "BTC/USD", 5, null),
  ],
  spillover_trust: { grade: "rough", reason: "Some pairs have as few as 9 past episodes." },
  weekends: [
    {
      symbol: "SPY",
      weekends: 299,
      correlation: 0.47,
      low: 0.38,
      high: 0.56,
      slope: 0.08,
      p_value: 1e-17,
      p_adjusted: 1e-17,
      gap_after_worst: -0.01,
      gap_usual: 0,
      worst_count: 30,
      verdict: "moves with",
    },
    { symbol: "GLD", weekends: 299, worst_count: 30, verdict: "no measurable link", slope: 0.02 },
  ],
  weekend_now: {
    since: "2026-10-02T20:00:00Z",
    as_of: "2026-10-04T18:00:00Z",
    bitcoin_move: Math.log(1.02),
  },
  weekend_trust: { grade: "solid", reason: "Measured on 299 or more past weekends." },
};

function show(path: string) {
  state.data = DATA;
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="together/:section?" element={<TogetherPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("TogetherPage", () => {
  afterEach(cleanup);

  it("opens with what was found, and only claims the spillovers that were measured", () => {
    const { container } = show("/together");
    expect(screen.getByText(/Bitcoin and Gold have moved fairly closely together/)).toBeVisible();
    expect(screen.getByText("0.53")).toBeVisible();
    expect(
      screen.getByText(/After Gold turned turbulent, US stocks' daily swings were 1.6 times/),
    ).toBeVisible();
    expect(screen.queryByText(/After Bitcoin turned turbulent/)).toBeNull();
    expect(screen.getByText(/US stocks has tended to open in the same direction/)).toBeVisible();
    expect(screen.getByText(/Gold's Monday open has had no measurable link/)).toBeVisible();
    expect(screen.getByText("+2.00%")).toBeVisible();
    expect(container.textContent).not.toMatch(/\b(buy|sell|you should)\b/i);
  });

  it("gives sample sizes by state and withholds a reading with too few days", () => {
    show("/together/pairs");
    expect(screen.getByText(/512 days/)).toBeVisible();
    expect(screen.getByText(/too few days to say/)).toBeVisible();
    expect(screen.getByText(/has a 95% range of\s+0.36 to 0.67/)).toBeVisible();
    expect(
      screen.getByText(/Bitcoin's move from Friday's close to Monday's\s+close/),
    ).toBeVisible();
  });

  it("says when a pair has too few episodes, and that this is not cause", () => {
    show("/together/spillovers");
    expect(
      screen.getByText(/Gold has turned turbulent only 9 times, too few to say/),
    ).toBeVisible();
    expect(screen.getByText("1 of 3 pairs show larger swings afterwards")).toBeVisible();
    expect(screen.getByText(/does not show that one causes the other/)).toBeVisible();
    expect(screen.getByText(/Why rough:/)).toBeVisible();
  });

  it("shows the current weekend move and what has followed moves like it", () => {
    show("/together/weekends");
    expect(screen.getByText("+2.00%")).toBeVisible();
    expect(screen.getByText("+0.16%")).toBeVisible(); // 8% of a 2% move
    expect(screen.getByText(/Single weekends vary widely/)).toBeVisible();
    expect(screen.getAllByText(/299 weekends/)).toHaveLength(2);
  });

  it("colours the grid and states its sample", () => {
    show("/together/grid");
    expect(screen.getAllByText("0.53")).toHaveLength(2);
    expect(screen.getByText(/on the 90 trading\s+days/)).toBeVisible();
  });
});

describe("relationship wording", () => {
  const name = (symbol: string) => ({ GLD: "Gold", SPY: "US stocks" })[symbol] ?? symbol;

  it("describes a correlation in plain words", () => {
    expect(linkWords(0.05)).toBe("have moved almost independently");
    expect(linkWords(0.3)).toBe("have moved loosely together");
    expect(linkWords(-0.55)).toBe("have moved fairly closely in opposite directions");
    expect(linkWords(0.85)).toBe("have moved closely together");
  });

  it("states no spillover and no link without dressing them up", () => {
    expect(spillSentence(spill("SPY", "GLD", 5, 0.99), name)).toBe(
      "After US stocks turned turbulent, Gold's swings were not measurably different from usual.",
    );
    expect(
      weekendSentence(
        { symbol: "GLD", weekends: 12, worst_count: 0, verdict: "not enough weekends" },
        name,
      ),
    ).toMatch(/too few weekends/);
  });

  it("draws a line with a gap where a value is missing", () => {
    expect(correlationPath([1, null, -1, 0], 30, 100)).toBe("M0.0,0.0 M20.0,100.0 L30.0,50.0");
  });

  it("names the strongest driver or says none is measurable", () => {
    const window: Drivers["windows"][number] = {
      window: 250,
      drivers: [
        { symbol: "UUP", coefficient: -0.006, low: -0.01, high: -0.003, verdict: "moves against" },
        {
          symbol: "TLT",
          coefficient: -0.002,
          low: -0.005,
          high: 0.001,
          verdict: "no measurable link",
        },
      ],
      r_squared: 0.25,
      first_day: "2025-10-01",
      last_day: "2026-10-02",
      history: [],
      out_of_sample: null,
      baseline: "SPY",
      strongest: "UUP",
    };
    expect(driverHeadline(window, { UUP: "US dollar" })).toBe("Moving most against US dollar");
    expect(driverHeadline({ ...window, strongest: null }, {})).toBe(
      "No outside force shows a measurable link right now",
    );
  });
});
