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
  together: undefined as unknown,
  setTarget: undefined as unknown,
}));

vi.mock("../api/queries", () => ({
  usePortfolio: () => ({ data: state.portfolio, isPending: false, isError: false }),
  usePortfolioAnalysis: () => ({ data: state.analysis }),
  useRelationships: () => ({ data: state.together }),
  useSetTarget: () => ({ mutate: state.setTarget, isPending: false, isError: false }),
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
  binance_available: false,
  leveraged: [],
  wallets: [],
};

const ANALYSIS: PortfolioAnalysis = {
  as_of: "2026-10-02T20:00:00Z",
  model_version: "portfolio-risk-1",
  covered_value: 10000,
  unmeasured: [],
  young: [],
  risk_level: { label: "high", ratio: 1.6, references: { SPY: 1, "BTC/USD": 3.4 } },
  drivers: null,
  driver_names: {},
  states: [
    { symbol: "BTC/USD", market: "BTC/USD", label: "calm", weight: 0.4 },
    { symbol: "SPY", market: "SPY", label: "turbulent", weight: 0.6 },
  ],
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
    established_volatility: 0.016,
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

  it("opens with figures and pictures, in percent and in money", () => {
    show("/portfolio");
    expect(screen.getAllByText("$10,000")).toHaveLength(2); // the header and the first tile
    expect(screen.getByText("±$160.00")).toBeVisible();
    expect(screen.getByText("±1.60% of the whole")).toBeVisible();
    // Money and risk as two rings of one donut, with the same split as a table beside it.
    expect(
      screen.getByRole("img", {
        name: "Money: Bitcoin 40%, US stocks 60%. Risk: Bitcoin 82%, US stocks 18%.",
      }),
    ).toBeVisible();
    expect(screen.getByText("82%")).toBeVisible();
    // The risk level, on a scale an investor can place.
    expect(screen.getByText("high")).toBeVisible();
    expect(screen.getByText("1.6× the daily movement of US stocks")).toBeVisible();
    expect(
      screen.getByRole("img", { name: "Your mix swings 1.60 times as much as US stocks" }),
    ).toBeVisible();
    expect(screen.getByText("$250.00")).toBeVisible();
    expect(screen.getByText("2.5%, passed on about 1 day in 20")).toBeVisible();
    // Every replayed episode is a bar; a partial one is marked.
    expect(screen.getByText("Old crash (partial)")).toBeVisible();
    expect(screen.getByText("−29.00%")).toBeVisible();
    expect(screen.queryByText("Long ago")).toBeNull(); // not replayed, so not drawn
    expect(
      screen
        .getAllByRole("link")
        .filter((a) => a.classList.contains("tile"))
        .map((a) => a.getAttribute("href")),
    ).toEqual([
      "/portfolio/sources",
      "/portfolio/sources",
      "/portfolio/sources",
      "/portfolio/limits",
      "/together",
      "/portfolio/episodes",
    ]);
  });

  it("says which holdings the risk figures leave out, and prices risk on the rest", () => {
    state.analysis = {
      ...ANALYSIS,
      value: 12500,
      covered_value: 10000,
      unmeasured: [{ symbol: "PURR", name: "PURR", weight: 0.2, days: 210 }],
    };
    show("/portfolio");
    expect(screen.getByText(/is not in the risk figures yet/)).toBeVisible();
    expect(screen.getByText(/210 of the 250 days of prices needed/)).toBeVisible();
    expect(screen.getByText(/describe the other 80%/)).toBeVisible();
    // The loss in money is a share of the part that is measured, not of everything.
    expect(screen.getByText("$250.00")).toBeVisible();
    expect(screen.getAllByText("$12,500")).toHaveLength(2);
  });

  it("says when a newer holding's risk is an estimate from a short record", () => {
    state.analysis = {
      ...ANALYSIS,
      young: [{ symbol: "PURR", name: "PURR", weight: 0.01, days: 208 }],
    };
    show("/portfolio");
    expect(screen.getByText(/is a newer holding with/)).toBeVisible();
    expect(screen.getByText(/208 days of prices/)).toBeVisible();
    expect(screen.getByText(/scaled up for it/)).toBeVisible();
  });

  it("ties the holdings to the state of their markets and to the weekend", () => {
    state.together = {
      weekend_now: {
        since: "2026-10-02T20:00:00Z",
        as_of: "2026-10-04T10:00:00Z",
        bitcoin_move: Math.log(1.05),
      },
      weekends: [
        { symbol: "SPY", verdict: "moves with", slope: 0.08, weekends: 299, worst_count: 30 },
      ],
    };
    show("/portfolio");
    expect(screen.getByText("60% in turbulence")).toBeVisible();
    expect(screen.getByText("turbulent")).toBeVisible();
    expect(screen.getByText("Bitcoin since the last close")).toBeVisible();
    expect(screen.getByText("+5.00%")).toBeInTheDocument();
    // 8% of a 5% move on a $6,000 holding.
    expect(screen.getByText(/\$24\.00\s+up/)).toBeVisible();
    state.together = undefined;
  });

  it("offers Binance only when a key is configured, and shows leveraged exposure", () => {
    show("/portfolio/holdings");
    expect(screen.queryByRole("button", { name: "Read from Binance" })).toBeNull();
    cleanup();
    state.portfolio = {
      ...PORTFOLIO,
      binance_available: true,
      leveraged: [
        {
          symbol: "BTC/USD",
          quantity: -0.2,
          leverage: 5,
          entry_price: 90000,
          mark_price: 80000,
          liquidation_price: 100000,
          distance_to_liquidation: 0.25,
        },
      ],
    };
    show("/portfolio/holdings");
    fireEvent.click(screen.getByRole("button", { name: "Read from Binance" }));
    expect(state.mutate).toHaveBeenCalledWith({ binance: true }, expect.anything());
    expect(screen.getByText("25.0% from liquidation")).toBeInTheDocument();
    expect(screen.getByText(/short 0.2 at\s+5× leverage/)).toBeInTheDocument();
  });

  it("never tells the reader what to do", () => {
    for (const path of [
      "/portfolio",
      "/portfolio/sources",
      "/portfolio/limits",
      "/together",
      "/portfolio/episodes",
    ]) {
      const { container } = show(path);
      expect(container.textContent).not.toMatch(/\b(buy|sell|you should)\b/i);
      cleanup();
    }
  });

  it("shows each holding's share of the money beside its share of the risk", () => {
    show("/portfolio/sources");
    expect(screen.getByText("Bitcoin: 40% of the money, 82% of the risk")).toBeInTheDocument();
    expect(screen.getByText("Why solid")).toBeInTheDocument();
    expect(screen.getAllByText("0.31", { selector: "td" })).toHaveLength(2);
    expect(screen.getByText("-42.0%")).toBeInTheDocument();
    expect(screen.getByText(/Measured on 1,443 trading days/)).toBeInTheDocument();
  });

  it("marks a loss limit that did not hold as unreliable", () => {
    show("/portfolio/limits");
    expect(
      screen.getByText("Loss limit for 19 in 20 periods of 1 market session"),
    ).toBeInTheDocument();
    expect(screen.getByText("4.5%")).toBeInTheDocument();
    expect(screen.getAllByText(/Treat it as unreliable/)).toHaveLength(1);
    expect(screen.getByText(/over 1,172 periods of 1 market session/)).toBeInTheDocument();
  });

  it("names missing holdings in a partial episode and says when one could not be replayed", () => {
    show("/portfolio/episodes");
    expect(screen.getByText(/Partial: no prices for Bitcoin in this period/)).toBeInTheDocument();
    expect(screen.getByText(/cover the other 60% of the\s+portfolio/)).toBeInTheDocument();
    expect(screen.getByText(/Not replayed: none of the holdings has prices/)).toBeInTheDocument();
  });

  it("asks for holdings when there are none", () => {
    state.portfolio = { ...PORTFOLIO, holdings: [] };
    state.analysis = null;
    show("/portfolio/limits");
    expect(screen.getByText(/Add your holdings to see this/)).toBeInTheDocument();
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
    expect(
      screen.getByText(/Each row needs an asset and a quantity above zero/),
    ).toBeInTheDocument();
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

  it("sets Binance's own totals beside what RADAR found, and says when money is missing", () => {
    const wallets = [
      { name: "Spot", value: 90.42 },
      { name: "Funding", value: 4.19 },
      { name: "Earn", value: 306.24 },
    ];
    state.portfolio = { ...PORTFOLIO, wallets };
    state.analysis = { ...ANALYSIS, value: 363.24 };
    show("/portfolio/holdings");
    expect(screen.getByText("$400.85")).toBeVisible(); // Binance's total
    expect(screen.getAllByText("$363.24")).toHaveLength(2); // the page header, and what RADAR found
    expect(screen.getByText("Earn wallet")).toBeVisible();
    expect(screen.getByText("$37.61 not found")).toBeVisible();
    expect(screen.getByText(/That money is in none of\s+the figures/)).toBeVisible();

    // A small difference is prices moving, not missing money.
    cleanup();
    state.analysis = { ...ANALYSIS, value: 398.0 };
    show("/portfolio/holdings");
    expect(screen.getByText("Everything accounted for")).toBeVisible();
    expect(screen.queryByText(/not found/)).toBeNull();

    // Typed-in holdings have nothing to be checked against.
    cleanup();
    state.portfolio = PORTFOLIO;
    show("/portfolio/holdings");
    expect(screen.queryByText("Checked against Binance")).toBeNull();
  });

  it("sends an unknown page back to the summary", () => {
    show("/portfolio/nonsense");
    expect(screen.getByRole("region", { name: "In brief" })).toBeInTheDocument();
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
