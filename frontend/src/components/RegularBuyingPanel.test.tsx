import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Portfolio, PortfolioAnalysis } from "../api/client";
import { RegularBuyingPanel } from "./RegularBuyingPanel";

const state = vi.hoisted(() => ({
  simulate: undefined as unknown,
  data: undefined as unknown,
  lookup: undefined as unknown,
  lookupError: undefined as unknown,
}));
vi.mock("../api/queries", () => ({
  useRegularBuying: () => ({
    mutate: state.simulate,
    data: state.data,
    isPending: false,
    isError: false,
  }),
  useLookup: () => ({
    mutate: state.lookup,
    isPending: false,
    isError: state.lookupError !== undefined,
    error: state.lookupError,
  }),
}));

const PORTFOLIO = {
  supported: [
    { symbol: "BTC/USD", name: "Bitcoin", asset_class: "crypto" },
    { symbol: "SPY", name: "US stocks (S&P 500)", asset_class: "stock" },
    { symbol: "GLD", name: "Gold", asset_class: "stock" },
    { symbol: "USD", name: "Cash (US dollars)", asset_class: "cash" },
  ],
} as unknown as Portfolio;

const ANALYSIS = {
  positions: [
    { symbol: "BTC/USD", name: "Bitcoin", weight: 0.1 },
    { symbol: "SPY", name: "US stocks (S&P 500)", weight: 0.3 },
    { symbol: "USD", name: "Cash (US dollars)", weight: 0.55 },
    { symbol: "PURR", name: "PURR", weight: 0.05 },
  ],
  // A newer holding cannot be simulated yet, so the plan does not start with it.
  young: [{ symbol: "PURR", name: "PURR", weight: 0.05, days: 208 }],
} as unknown as PortfolioAnalysis;

const path = (end: number) => Array.from({ length: 252 }, (_, i) => (end * (i + 1)) / 252);
const RESULT = {
  weights: { "BTC/USD": 0.25, SPY: 0.75 },
  names: { "BTC/USD": "Bitcoin", SPY: "US stocks (S&P 500)" },
  first_day: "2021-01-05",
  last_day: "2026-10-05",
  trust: { grade: "fair", reason: "The 80% range held in 4 of 4 past 252-session forecasts." },
  result: {
    model_version: "regular-buying-1",
    n_paths: 5000,
    block: 10,
    n_days: 1444,
    separate_periods: 5,
    amount: 100,
    every: 21,
    purchases: 12,
    sessions: 252,
    paid_in: 1200,
    plan: {
      quantiles: { "0.05": 1050, "0.25": 1180, "0.5": 1290, "0.75": 1400, "0.95": 1600 },
      below_paid_in: 0.28,
    },
    at_once: {
      quantiles: { "0.05": 950, "0.25": 1200, "0.5": 1380, "0.75": 1600, "0.95": 1950 },
      below_paid_in: 0.24,
    },
    plan_ahead: 0.36,
    fan: {
      "0.05": path(1050),
      "0.25": path(1180),
      "0.5": path(1290),
      "0.75": path(1400),
      "0.95": path(1600),
    },
    paid_in_path: Array.from({ length: 252 }, (_, i) => 100 * (Math.floor(i / 21) + 1)),
    coverage: [
      { level: 0.5, n: 4, inside: 2 },
      { level: 0.8, n: 4, inside: 4 },
      { level: 0.95, n: 4, inside: 4 },
    ],
  },
};

describe("RegularBuyingPanel", () => {
  beforeEach(() => {
    state.simulate = vi.fn();
    state.lookup = vi.fn();
    state.data = undefined;
    state.lookupError = undefined;
  });
  afterEach(cleanup);

  it("starts from what is held and lets every input be chosen", () => {
    render(<RegularBuyingPanel portfolio={PORTFOLIO} analysis={ANALYSIS} />);
    // Bitcoin and stocks in the proportions held, cash left out.
    expect(screen.getByLabelText("Bitcoin share of each purchase, percent")).toHaveValue(25);
    expect(screen.getByLabelText("US stocks share of each purchase, percent")).toHaveValue(75);
    expect(screen.getByText("12 purchases of $100.00: $1,200 in all")).toBeVisible();
    expect(screen.queryByLabelText("PURR share of each purchase, percent")).toBeNull();

    fireEvent.change(screen.getByLabelText("Dollars per purchase"), { target: { value: "50" } });
    fireEvent.click(screen.getByRole("button", { name: "Every week" }));
    fireEvent.click(screen.getByRole("button", { name: "6 months" }));
    fireEvent.click(screen.getByRole("button", { name: "Add Gold" }));
    fireEvent.change(screen.getByLabelText("Gold share of each purchase, percent"), {
      target: { value: "20" },
    });
    expect(screen.getByText("25 purchases of $50.00: $1,250 in all")).toBeVisible();
    expect(screen.getByText(/add up to 120%; they are scaled to 100%/)).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Run the simulation" }));
    expect(state.simulate).toHaveBeenCalledWith({
      weights: { "BTC/USD": 25, SPY: 75, GLD: 20 },
      amount: 50,
      every: 5,
      purchases: 25,
    });
  });

  it("starts from the first known asset when nothing is held", () => {
    render(<RegularBuyingPanel portfolio={PORTFOLIO} />);
    expect(screen.getByLabelText("Bitcoin share of each purchase, percent")).toHaveValue(100);
    fireEvent.change(screen.getByLabelText("Dollars per purchase"), { target: { value: "0" } });
    expect(screen.getByRole("button", { name: "Run the simulation" })).toBeDisabled();
  });

  it("shows the outcome in money beside putting it all in at once", () => {
    state.data = RESULT;
    const { container } = render(<RegularBuyingPanel portfolio={PORTFOLIO} analysis={ANALYSIS} />);
    expect(
      screen.getByText(
        "$1,200 paid in ends between $1,050 and $1,600 in 9 of 10 simulated futures",
      ),
    ).toBeVisible();
    expect(screen.getByText("$1,290")).toBeVisible();
    expect(screen.getByText("+7.50% on the money paid in")).toBeVisible();
    expect(screen.getByText("28%")).toBeVisible();
    expect(
      screen.getByRole("img", {
        name: "All at once on day one: 9 in 10 outcomes between $950.00 and $1,950",
      }),
    ).toBeVisible();
    expect(container.textContent).toMatch(/Buying bit by bit ended with more in 36% of/);
    // Four past cases is said to be very few.
    expect(container.textContent).toMatch(/of 4 earlier stretches.*held in 4\. That is very few/);
    expect(container.textContent).toMatch(/Only about 5 separate stretches/);
    expect(container.textContent).toMatch(/not what will happen/);
    expect(container.textContent).not.toMatch(/\b(buy now|sell|you should)\b/i);
  });

  it("brings in an asset by its ticker", () => {
    render(<RegularBuyingPanel portfolio={PORTFOLIO} analysis={ANALYSIS} />);
    const find = screen.getByRole("button", { name: "Find" });
    expect(find).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Ticker"), { target: { value: "nvda" } });
    expect(screen.getByLabelText("Ticker")).toHaveValue("NVDA");
    fireEvent.click(find);
    const [input, options] = (state.lookup as ReturnType<typeof vi.fn>).mock.calls[0] as [
      unknown,
      { onSuccess: (asset: { symbol: string; name: string }) => void },
    ];
    expect(input).toEqual({ ticker: "NVDA", kind: "stock" });

    // The lookup answers: the asset becomes a row and the box is cleared.
    fireEvent.click(screen.getByRole("button", { name: "Crypto" }));
    options.onSuccess({ symbol: "NVDA", name: "NVDA" });
    cleanup();
  });

  it("says why a ticker was not found", () => {
    state.lookupError = new Error("No stock prices were found for ZZZZ.");
    render(<RegularBuyingPanel portfolio={PORTFOLIO} />);
    expect(screen.getByRole("alert")).toHaveTextContent("No stock prices were found for ZZZZ.");
  });
});
