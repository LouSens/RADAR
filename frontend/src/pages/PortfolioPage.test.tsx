import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Portfolio, PortfolioAnalysis } from "../api/client";
import { largestImbalance, parseQuantity, worstEpisode } from "../lib/portfolio";
import { PortfolioPage } from "./PortfolioPage";

const state = vi.hoisted(() => ({
  portfolio: undefined as unknown,
  analysis: undefined as unknown,
  mutate: undefined as unknown,
}));

vi.mock("../api/queries", () => ({
  usePortfolio: () => ({ data: state.portfolio, isPending: false, isError: false }),
  usePortfolioAnalysis: () => ({ data: state.analysis }),
  useSavePortfolio: () => ({
    mutate: state.mutate,
    isPending: false,
    isError: false,
    isSuccess: false,
    data: undefined,
  }),
}));

const backtest = (breaches: number, expected: number, reliable = true) => ({
  method: "historical",
  level: 0.95,
  n: 1172,
  breaches,
  expected_breaches: expected,
  breach_rate: breaches / 1172,
  kupiec_p_value: 0.6,
  kupiec_p_adjusted: 0.8,
  clustering_p_value: 0.4,
  reliable,
  first_day: "2022-01-03",
  last_day: "2026-10-01",
});

const PORTFOLIO: Portfolio = {
  source: "manual",
  holdings: [
    { symbol: "BTC/USD", quantity: 0.05, tag: null },
    { symbol: "SPY", quantity: 6, tag: null },
  ],
  unsupported: [],
  supported: [
    { symbol: "BTC/USD", name: "Bitcoin", asset_class: "crypto" },
    { symbol: "SPY", name: "US stocks (S&P 500)", asset_class: "stock" },
  ],
  problem: null,
};

const ANALYSIS: PortfolioAnalysis = {
  as_of: "2026-10-02T20:00:00Z",
  model_version: "portfolio-risk-1",
  value: 10000,
  positions: [
    {
      symbol: "BTC/USD",
      name: "Bitcoin",
      quantity: 0.05,
      tag: null,
      price: 80000,
      value: 4000,
      weight: 0.4,
    },
    {
      symbol: "SPY",
      name: "US stocks (S&P 500)",
      quantity: 6,
      tag: null,
      price: 1000,
      value: 6000,
      weight: 0.6,
    },
  ],
  xray: {
    holdings: [
      { symbol: "BTC/USD", weight: 0.4, daily_volatility: 0.036, risk_share: 0.82 },
      { symbol: "SPY", weight: 0.6, daily_volatility: 0.011, risk_share: 0.18 },
    ],
    daily_volatility: 0.016,
    undiversified_volatility: 0.021,
    symbols: ["BTC/USD", "SPY"],
    correlation: [
      [1, 0.31],
      [0.31, 1],
    ],
    n_days: 1443,
    first_day: "2021-01-05",
    last_day: "2026-10-02",
    deepest_fall: { depth: -0.42, peak_day: "2021-11-09", trough_day: "2022-11-09" },
  },
  limits: [
    {
      horizon_days: 1,
      steps: 1,
      shown: "historical",
      levels: [
        {
          level: 0.95,
          methods: [
            {
              method: "historical",
              var: 0.025,
              expected_shortfall: 0.036,
              backtest: backtest(55, 58.6),
            },
          ],
        },
        {
          level: 0.99,
          methods: [
            {
              method: "historical",
              var: 0.045,
              expected_shortfall: 0.055,
              backtest: { ...backtest(25, 11.7, false), level: 0.99 },
            },
          ],
        },
      ],
    },
  ],
  stress: [
    {
      name: "Old crash",
      start: "2020-02-19",
      end: "2020-03-23",
      available: true,
      change: -0.34,
      deepest_fall: -0.34,
      worst_day: "2020-03-16",
      worst_day_change: -0.11,
      parts: [{ symbol: "SPY", change: -0.34, contribution: -0.34 }],
      missing: ["BTC/USD"],
      covered_weight: 0.6,
    },
    {
      name: "Rate rises",
      start: "2022-01-03",
      end: "2022-10-14",
      available: true,
      change: -0.29,
      deepest_fall: -0.31,
      worst_day: "2022-06-13",
      worst_day_change: -0.06,
      parts: [
        { symbol: "BTC/USD", change: -0.58, contribution: -0.232 },
        { symbol: "SPY", change: -0.097, contribution: -0.058 },
      ],
      missing: [],
      covered_weight: 1,
    },
    {
      name: "Long ago",
      start: "2010-01-01",
      end: "2010-02-01",
      available: false,
      parts: [],
      missing: ["BTC/USD", "SPY"],
      covered_weight: 0,
    },
  ],
  trust: {
    xray: { grade: "solid", reason: "Measured over 1,443 trading days." },
    risk: { grade: "fair", reason: "One limit held as stated and one did not." },
    stress: { grade: "fair", reason: "2 of 3 episodes could be replayed." },
  },
};

function show(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="portfolio/:section?" element={<PortfolioPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("PortfolioPage", () => {
  afterEach(() => {
    cleanup();
    state.portfolio = PORTFOLIO;
    state.analysis = ANALYSIS;
    state.mutate = vi.fn();
  });
  state.portfolio = PORTFOLIO;
  state.analysis = ANALYSIS;
  state.mutate = vi.fn();

  it("opens with the answers in sentences, in percent and in money", () => {
    show("/portfolio");
    expect(screen.getAllByText("$10,000")).toHaveLength(2); // the header and the sentence
    expect(screen.getByText("±1.60%")).toBeVisible();
    expect(screen.getByText("$160.00")).toBeVisible();
    expect(screen.getAllByText("40%")).toHaveLength(2); // of the money, and in the list
    expect(screen.getByText("82%")).toBeVisible(); // of the risk
    expect(screen.getByText("2.5%")).toBeVisible();
    expect(screen.getByText("$250.00")).toBeVisible();
    // The episode quoted is the worst one replayed with every holding, not the partial one.
    expect(screen.getByText(/Replayed through Rate rises, this mix/)).toBeVisible();
    expect(screen.getByText("−29.00%")).toBeVisible();
    expect(
      screen.getAllByRole("link", { name: "Evidence" }).map((a) => a.getAttribute("href")),
    ).toEqual([
      "/portfolio/holdings",
      "/portfolio/sources",
      "/portfolio/sources",
      "/portfolio/limits",
      "/portfolio/episodes",
    ]);
  });

  it("never tells the reader what to do", () => {
    for (const path of [
      "/portfolio",
      "/portfolio/sources",
      "/portfolio/limits",
      "/portfolio/episodes",
    ]) {
      const { container } = show(path);
      expect(container.textContent).not.toMatch(/\b(buy|sell|you should)\b/i);
      cleanup();
    }
  });

  it("shows each holding's share of the money beside its share of the risk", () => {
    show("/portfolio/sources");
    expect(screen.getByText("Bitcoin: 40% of the money, 82% of the risk")).toBeVisible();
    expect(screen.getByText(/Why solid:/)).toBeVisible();
    expect(screen.getAllByText("0.31", { selector: "td" })).toHaveLength(2);
    expect(screen.getByText("-42.0%")).toBeVisible();
    expect(screen.getByText(/Measured on 1,443 trading days/)).toBeVisible();
  });

  it("marks a loss limit that did not hold as unreliable", () => {
    show("/portfolio/limits");
    expect(screen.getByText("Loss limit for 19 in 20 periods of 1 market session")).toBeVisible();
    expect(screen.getByText("4.5%")).toBeVisible();
    expect(screen.getAllByText(/Treat it as unreliable/)).toHaveLength(1);
    expect(screen.getByText(/over 1,172 periods of 1 market session/)).toBeVisible();
  });

  it("names missing holdings in a partial episode and says when one could not be replayed", () => {
    show("/portfolio/episodes");
    expect(screen.getByText(/Partial: no prices for Bitcoin in this period/)).toBeVisible();
    expect(screen.getByText(/cover the other 60% of the\s+portfolio/)).toBeVisible();
    expect(screen.getByText(/Not replayed: none of the holdings has prices/)).toBeVisible();
  });

  it("asks for holdings when there are none", () => {
    state.portfolio = { ...PORTFOLIO, holdings: [] };
    state.analysis = null;
    show("/portfolio/limits");
    expect(screen.getByText(/Add your holdings to see this/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Go to holdings" })).toHaveAttribute(
      "href",
      "/portfolio/holdings",
    );
  });

  it("saves typed holdings and refuses a row without a quantity", () => {
    show("/portfolio/holdings");
    const save = screen.getByRole("button", { name: "Save holdings" });
    fireEvent.change(screen.getByLabelText("Quantity of holding 2"), { target: { value: "" } });
    expect(save).toBeDisabled();
    expect(screen.getByText(/Each row needs an asset and a quantity above zero/)).toBeVisible();
    fireEvent.change(screen.getByLabelText("Quantity of holding 2"), { target: { value: "7.5" } });
    fireEvent.click(save);
    expect(state.mutate).toHaveBeenCalledWith(
      {
        holdings: [
          { symbol: "BTC/USD", quantity: 0.05 },
          { symbol: "SPY", quantity: 7.5 },
        ],
      },
      expect.anything(),
    );
  });

  it("sends an unknown page back to the summary", () => {
    show("/portfolio/nonsense");
    expect(screen.getByText("In brief")).toBeVisible();
  });
});

describe("portfolio helpers", () => {
  it("finds the holding whose risk most exceeds its weight", () => {
    expect(largestImbalance(ANALYSIS.positions, ANALYSIS.xray)).toEqual({
      symbol: "BTC/USD",
      name: "Bitcoin",
      weight: 0.4,
      riskShare: 0.82,
    });
  });

  it("prefers complete episodes, and falls back to partial ones", () => {
    expect(worstEpisode(ANALYSIS.stress)?.name).toBe("Rate rises");
    expect(worstEpisode(ANALYSIS.stress.filter((e) => e.name !== "Rate rises"))?.name).toBe(
      "Old crash",
    );
    expect(worstEpisode([])).toBeUndefined();
  });

  it("accepts only quantities above zero", () => {
    expect(parseQuantity("1,250.5")).toBe(1250.5);
    expect(parseQuantity(" 0.05 ")).toBe(0.05);
    for (const bad of ["", "0", "-1", "abc", "1e999"]) expect(parseQuantity(bad)).toBeUndefined();
  });
});
