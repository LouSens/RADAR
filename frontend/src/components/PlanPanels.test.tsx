import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PortfolioAnalysis, PortfolioPlan } from "../api/client";
import { levelMix, levelNow, signalText } from "../lib/plan";
import { LevelsPanel, MixesPanel, targetSummary } from "./PlanPanels";

function must<T>(value: T | null | undefined): T {
  if (value == null) throw new Error("missing");
  return value;
}

const state = vi.hoisted(() => ({ mutate: undefined as unknown }));
vi.mock("../api/queries", () => ({
  useSetTarget: () => ({ mutate: state.mutate, isPending: false, isError: false }),
}));

const level = (
  name: "low" | "moderate" | "high",
  aim: number,
  cash: number,
  low: number,
  high: number,
) => ({
  level: name,
  aim,
  band_low: low,
  band_high: high,
  cash_share: cash,
  ratio: aim,
  reachable: true,
});

const mix = (method: string, vol: number, fall: number, btc: number) => ({
  method,
  n_days: 1194,
  first_day: "2021-12-31",
  last_day: "2026-10-02",
  rebalances: 56,
  daily_volatility: vol,
  deepest_fall: fall,
  turnover: 0.012,
  total_return: 0.2,
  cost_paid: 0.0007,
  weights_now: { "BTC/USD": btc, SPY: 1 - btc },
  path: [1, 1.05, 1.1, 1.2],
});

const PLAN: PortfolioPlan = {
  invested_ratio: 1.6,
  ratio: 0.4,
  now_ratio: 0.3,
  levels: [
    level("low", 0.25, 0.84, 0, 0.5),
    level("moderate", 0.75, 0.53, 0.5, 1),
    level("high", 1.5, 0.06, 1, 2),
  ],
  mixes: [
    mix("current", 0.0034, -0.094, 0.4),
    mix("equal", 0.0032, -0.089, 0.5),
    mix("min_variance", 0.0019, -0.045, 0.1),
  ] as PortfolioPlan["mixes"],
  target: null,
  target_plan: null,
  moves: [],
  in_band: null,
  signals: [],
  trust: { grade: "solid", reason: "Each mix was run through 1,194 trading days." },
};

const ANALYSIS = {
  covered_value: 400,
  value: 400,
  positions: [
    { symbol: "BTC/USD", name: "Bitcoin", weight: 0.1 },
    { symbol: "SPY", name: "US stocks (S&P 500)", weight: 0.15 },
    { symbol: "USD", name: "Cash (US dollars)", weight: 0.75 },
  ],
  xray: {
    symbols: ["BTC/USD", "SPY"],
    daily_volatility: 0.004,
    holdings: [
      { symbol: "BTC/USD", weight: 0.1, daily_volatility: 0.036, risk_share: 0.7 },
      { symbol: "SPY", weight: 0.15, daily_volatility: 0.011, risk_share: 0.3 },
      { symbol: "USD", weight: 0.75, daily_volatility: 0, risk_share: 0 },
    ],
  },
  limits: [
    {
      horizon_days: 1,
      shown: "historical",
      levels: [{ level: 0.95, methods: [{ method: "historical", var: 0.006 }] }],
    },
  ],
  trust: { xray: { grade: "solid", reason: "Measured over 1,443 trading days." } },
  plan: PLAN,
} as unknown as PortfolioAnalysis;

const withTarget = (extra: Partial<PortfolioPlan>): PortfolioAnalysis =>
  ({
    ...ANALYSIS,
    plan: {
      ...PLAN,
      target: { level: "moderate", split: "current", set_at: "2026-10-07T04:00:00Z" },
      target_plan: PLAN.levels[1],
      moves: [
        {
          symbol: "BTC/USD",
          current_weight: 0.1,
          target_weight: 0.188,
          change_value: 35.2,
          drifted: true,
        },
        {
          symbol: "SPY",
          current_weight: 0.15,
          target_weight: 0.282,
          change_value: 52.8,
          drifted: true,
        },
        {
          symbol: "USD",
          current_weight: 0.75,
          target_weight: 0.53,
          change_value: -88,
          drifted: true,
        },
      ],
      in_band: false,
      signals: [
        { kind: "risk_below_target", value: 0.3, against: 0.5, symbols: [] },
        { kind: "drift", value: 0.22, against: 0.05, symbols: ["BTC/USD", "SPY", "USD"] },
      ],
      ...extra,
    },
  }) as unknown as PortfolioAnalysis;

describe("LevelsPanel", () => {
  beforeEach(() => {
    state.mutate = vi.fn();
  });
  afterEach(cleanup);

  it("shows what each level would look like with these holdings, in money", () => {
    render(<LevelsPanel analysis={ANALYSIS} />);
    expect(screen.getByText("Today the mix reads low. No target chosen")).toBeVisible();
    for (const name of ["low risk", "moderate risk", "high risk"]) {
      expect(screen.getByRole("region", { name })).toBeVisible();
    }
    expect(screen.getByText("You are here")).toBeVisible();
    // Moderate: 53% in cash of $400; today's ±$1.60 day scaled by 0.75 / 0.4.
    expect(screen.getByText("53% · $212.00")).toBeVisible();
    expect(screen.getByText("±$3.00")).toBeVisible();
    expect(screen.getByText("$4.50")).toBeVisible(); // the 1-in-20 loss, scaled the same way
    expect(
      screen.getByRole("img", {
        name: /^moderate risk mix: Bitcoin 19%, US stocks 28%, Cash 53%$/,
      }),
    ).toBeVisible();
  });

  it("sets a level as the target, and clears it from the chosen card", () => {
    const { rerender } = render(<LevelsPanel analysis={ANALYSIS} />);
    fireEvent.click(must(screen.getAllByRole("button", { name: "Set as my target" })[1]));
    expect(state.mutate).toHaveBeenCalledWith({ level: "moderate", split: "current" });

    rerender(<LevelsPanel analysis={withTarget({})} />);
    expect(screen.getByText("Your target is moderate; today the mix reads low")).toBeVisible();
    expect(screen.getByText("Your target")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Clear target" }));
    expect(state.mutate).toHaveBeenLastCalledWith({ level: null, split: "current" });
  });

  it("states the distance from the target without saying what to do about it", () => {
    const { container } = render(<LevelsPanel analysis={withTarget({})} />);
    expect(screen.getByText("Distance from your target")).toBeVisible();
    expect(
      screen.getByText(
        /moving 0.30× as much as US stocks, below your target's lower edge of 0.50×/,
      ),
    ).toBeVisible();
    expect(
      screen.getByText(/more than 5 points from target; the widest gap is 22 points/),
    ).toBeVisible();
    expect(screen.getByText("+$35.20")).toBeVisible();
    expect(screen.getByText("−$88.00")).toBeVisible();
    expect(screen.getByText("75% now · target 53%")).toBeVisible();
    expect(container.textContent).not.toMatch(/\b(buy|sell|you should)\b/i);
  });

  it("says so when nothing has moved, and when a level is out of reach", () => {
    const calm = withTarget({ signals: [], moves: [], in_band: true });
    const { rerender } = render(<LevelsPanel analysis={calm} />);
    expect(screen.getByText("Within your target on every measure.")).toBeVisible();

    const stuck = {
      ...ANALYSIS,
      plan: {
        ...PLAN,
        invested_ratio: 0.9,
        levels: [
          PLAN.levels[0],
          PLAN.levels[1],
          { ...PLAN.levels[2], reachable: false, cash_share: 0, ratio: 0.9 },
        ],
      },
    } as unknown as PortfolioAnalysis;
    rerender(<LevelsPanel analysis={stuck} />);
    expect(screen.getByText(/out of reach without borrowing/)).toBeVisible();
  });
});

describe("MixesPanel", () => {
  beforeEach(() => {
    state.mutate = vi.fn();
  });
  afterEach(cleanup);

  it("compares the mixes on movement and deepest fall, with the split of each", () => {
    render(<MixesPanel analysis={ANALYSIS} />);
    expect(screen.getByText("Smallest movement moved least: ±0.19% a day")).toBeVisible();
    expect(screen.getAllByText("As it is now").length).toBeGreaterThan(1);
    expect(screen.getByText("-9.4%")).toBeVisible();
    expect(
      screen.getByRole("img", { name: /^Smallest movement split: Bitcoin 10%, US stocks 90%$/ }),
    ).toBeVisible();
    expect(screen.getByText("Bitcoin 10% · US stocks 90%")).toBeVisible();
    // Without a target there is nothing to apply a split to.
    expect(screen.getByText("Choose a risk level first to use one of these splits.")).toBeVisible();
    for (const button of screen.getAllByRole("button", { name: /Use for my target|In use/ })) {
      expect(button).toBeDisabled();
    }
  });

  it("applies a split to the chosen target and never to anything else", () => {
    render(<MixesPanel analysis={withTarget({})} />);
    expect(screen.getByRole("button", { name: "In use" })).toBeDisabled();
    fireEvent.click(must(screen.getAllByRole("button", { name: "Use for my target" })[1]));
    expect(state.mutate).toHaveBeenCalledWith({ level: "moderate", split: "min_variance" });
  });

  it("explains itself when there is nothing to compare", () => {
    const single = { ...ANALYSIS, plan: { ...PLAN, mixes: [] } } as unknown as PortfolioAnalysis;
    render(<MixesPanel analysis={single} />);
    expect(screen.getByText(/needs at least two holdings/)).toBeVisible();
  });
});

describe("plan helpers", () => {
  it("reads the level from current conditions when they are known", () => {
    expect(levelNow(PLAN)).toBe("low");
    expect(levelNow({ ...PLAN, now_ratio: 0.8 })).toBe("moderate");
    expect(levelNow({ ...PLAN, now_ratio: null, ratio: 1.2 })).toBe("high");
    expect(levelNow({ ...PLAN, now_ratio: 2.4 })).toBe("very high");
  });

  it("keeps the holdings' proportions and changes only the cash share", () => {
    const mixAtModerate = levelMix(ANALYSIS, PLAN, must(PLAN.levels[1]));
    expect(mixAtModerate.USD).toBe(0.53);
    expect(must(mixAtModerate["BTC/USD"]) / must(mixAtModerate.SPY)).toBeCloseTo(0.1 / 0.15);
    const total = Object.values(mixAtModerate).reduce((a, b) => a + b, 0);
    expect(total).toBeCloseTo(1);
  });

  it("summarises the target for the first view", () => {
    expect(targetSummary(PLAN).figure).toBe("No target yet");
    expect(targetSummary(withTarget({}).plan).figure).toBe("2 things have moved");
    expect(targetSummary(withTarget({ signals: [] }).plan)).toEqual({
      figure: "On target",
      note: "Target: moderate risk",
      level: "moderate",
    });
    // Turbulence is information about the market, not a move away from the target.
    const rough = withTarget({
      signals: [{ kind: "turbulent", value: 0.1, against: 0, symbols: ["BTC/USD"] }],
    });
    expect(targetSummary(rough.plan).figure).toBe("On target");
    expect(signalText(must(must(rough.plan).signals[0]), () => "Bitcoin")).toBe(
      "10% of your money is in a market that is turbulent right now (Bitcoin).",
    );
  });
});
