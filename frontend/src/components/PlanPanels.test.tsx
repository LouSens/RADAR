import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PortfolioAnalysis, PortfolioPlan } from "../api/client";
import { levelMix, levelNow, signalText } from "../lib/plan";
import { LevelsPanel, MixesPanel, targetSummary } from "./PlanPanels";

function must<T>(value: T | null | undefined): T {
  if (value == null) throw new Error("missing");
  return value;
}

const state = vi.hoisted(() => ({
  mutate: undefined as unknown,
  tryMix: undefined as unknown,
  tried: undefined as unknown,
}));
vi.mock("../api/queries", () => ({
  useSetTarget: () => ({
    mutate: state.mutate,
    isPending: false,
    isError: false,
    isSuccess: false,
  }),
  useWhatIf: () => ({
    mutate: state.tryMix,
    data: state.tried,
    isPending: false,
    isError: false,
  }),
  usePortfolio: () => ({
    data: {
      supported: [
        { symbol: "BTC/USD", name: "Bitcoin", asset_class: "crypto" },
        { symbol: "SPY", name: "US stocks (S&P 500)", asset_class: "stock" },
        { symbol: "GLD", name: "Gold", asset_class: "stock" },
        { symbol: "USD", name: "Cash (US dollars)", asset_class: "cash" },
      ],
    },
  }),
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
  risk_level: { label: "low", ratio: 0.4, references: { SPY: 1 } },
  value: 400,
  positions: [
    { symbol: "BTC/USD", name: "Bitcoin", weight: 0.1 },
    { symbol: "SPY", name: "US stocks (S&P 500)", weight: 0.15 },
    { symbol: "USD", name: "Cash (US dollars)", weight: 0.75 },
  ],
  xray: {
    symbols: ["BTC/USD", "SPY"],
    daily_volatility: 0.004,
    deepest_fall: { depth: -0.11, peak_day: "2021-11-09", trough_day: "2022-11-09" },
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

const TRIED = {
  value: 400,
  weights: { "BTC/USD": 0.2, SPY: 0.3, USD: 0.5 },
  names: { "BTC/USD": "Bitcoin", SPY: "US stocks (S&P 500)", USD: "Cash (US dollars)" },
  daily_volatility: 0.008,
  ratio: 0.8,
  level: "moderate",
  limit_95: 0.012,
  limit_99: 0.02,
  deepest_fall: -0.22,
  risk_shares: { "BTC/USD": 0.7, SPY: 0.3, USD: 0 },
  n_days: 1443,
  young: [],
  unmeasured: [],
};

describe("LevelsPanel", () => {
  beforeEach(() => {
    state.mutate = vi.fn();
    state.tryMix = vi.fn();
    state.tried = undefined;
  });
  afterEach(cleanup);

  it("starts from the portfolio as it is and lets every share be changed", () => {
    render(<LevelsPanel analysis={ANALYSIS} />);
    expect(screen.getByText("Today your mix reads low. Try another to compare")).toBeVisible();
    expect(screen.getByLabelText("Bitcoin share, percent")).toHaveValue(10);
    expect(screen.getByLabelText("US stocks share, percent")).toHaveValue(15);
    expect(screen.getByText("75% · $300.00")).toBeVisible(); // cash is what is left

    fireEvent.change(screen.getByLabelText("Bitcoin share, percent"), { target: { value: "30" } });
    expect(screen.getByText("55% · $220.00")).toBeVisible();
    expect(screen.getByLabelText("Bitcoin share, slider")).toHaveValue("30");

    fireEvent.click(screen.getByRole("button", { name: "Work out the risk" }));
    expect(state.tryMix).toHaveBeenCalledWith({ weights: { "BTC/USD": 0.3, SPY: 0.15 } });
  });

  it("refuses shares that add up to more than everything", () => {
    render(<LevelsPanel analysis={ANALYSIS} />);
    fireEvent.change(screen.getByLabelText("Bitcoin share, percent"), { target: { value: "95" } });
    expect(screen.getByText("10% too much")).toBeVisible();
    expect(screen.getByRole("button", { name: "Work out the risk" })).toBeDisabled();
  });

  it("offers the levels and the other splits as starting points, not as decisions", () => {
    render(<LevelsPanel analysis={ANALYSIS} />);
    fireEvent.click(screen.getByRole("button", { name: "Moderate risk" }));
    // 47% invested, in today's proportions of 10 to 15.
    expect(screen.getByLabelText("Bitcoin share, percent")).toHaveValue(18.8);
    expect(screen.getByLabelText("US stocks share, percent")).toHaveValue(28.2);
    expect(state.tryMix).toHaveBeenCalledWith({ weights: { "BTC/USD": 0.188, SPY: 0.282 } });

    fireEvent.click(screen.getByRole("button", { name: "Smallest movement" }));
    // Today's 25% invested, split 10 to 90.
    expect(screen.getByLabelText("Bitcoin share, percent")).toHaveValue(2.5);
    expect(screen.getByLabelText("US stocks share, percent")).toHaveValue(22.5);
  });

  it("lets an asset not held yet be added, and one be removed", () => {
    render(<LevelsPanel analysis={ANALYSIS} />);
    fireEvent.change(screen.getByLabelText("Add another asset"), { target: { value: "GLD" } });
    expect(screen.getByLabelText("Gold share, percent")).toHaveValue(0);
    fireEvent.click(screen.getByRole("button", { name: "Remove Bitcoin" }));
    expect(screen.queryByLabelText("Bitcoin share, percent")).toBeNull();
    expect(screen.getByText("85% · $340.00")).toBeVisible();
  });

  it("sets the tried mix beside the portfolio as it is, in money", () => {
    state.tried = TRIED;
    const { container } = render(<LevelsPanel analysis={ANALYSIS} />);
    expect(screen.getByText("moderate")).toBeVisible();
    expect(screen.getByText(/0.80× the daily movement of US stocks/)).toBeVisible();
    expect(screen.getByText("0.40×")).toBeVisible(); // now
    expect(screen.getByText("0.80×")).toBeVisible(); // this mix
    expect(screen.getByText("±$1.60")).toBeVisible();
    expect(screen.getByText("±$3.20")).toBeVisible();
    expect(screen.getByText("$2.40")).toBeVisible(); // today's loss on 1 day in 20
    expect(screen.getByText("$4.80")).toBeVisible();
    expect(screen.getByText("$8.00")).toBeVisible(); // 1 day in 100
    expect(screen.getByText("-22.0%")).toBeVisible();
    expect(
      screen.getByRole("img", {
        name: /^Share of the risk in this mix: Bitcoin 70%, US stocks 30%$/,
      }),
    ).toBeVisible();
    expect(container.textContent).not.toMatch(/\b(buy|sell|you should)\b/i);

    fireEvent.click(screen.getByRole("button", { name: "Set this mix as my target" }));
    expect(state.mutate).toHaveBeenCalledWith({ weights: TRIED.weights });
  });

  it("states the distance from the target without saying what to do about it", () => {
    const { container } = render(<LevelsPanel analysis={withTarget({})} />);
    expect(
      screen.getByText("Your target is moderate risk; today your mix reads low"),
    ).toBeVisible();
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

  it("names a mix of the user's own as the target, and says when nothing has moved", () => {
    const own = withTarget({
      target: {
        level: null,
        split: "current",
        weights: { "BTC/USD": 0.1, SPY: 0.15 },
        set_at: null,
      },
      target_plan: null,
      signals: [],
      moves: [
        {
          symbol: "BTC/USD",
          current_weight: 0.1,
          target_weight: 0.1,
          change_value: 0,
          drifted: false,
        },
      ],
      in_band: null,
    });
    render(<LevelsPanel analysis={own} />);
    expect(
      screen.getByText("Your target is a mix of your own; today your mix reads low"),
    ).toBeVisible();
    expect(screen.getByText("Within your target on every measure.")).toBeVisible();
    expect(targetSummary(own.plan).note).toBe("Target: a mix of your own");
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
    expect(screen.getByText(/These splits apply to a risk-level target/)).toBeVisible();
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
