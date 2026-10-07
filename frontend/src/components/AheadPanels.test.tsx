import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PortfolioAnalysis } from "../api/client";
import { RangeAheadPanel, SleevesPanel } from "./AheadPanels";

const state = vi.hoisted(() => ({ mutate: undefined as unknown }));
vi.mock("../api/queries", () => ({
  useSetTags: () => ({ mutate: state.mutate, isPending: false, isError: false }),
}));

const CHANCES = Array.from({ length: 101 }, (_, i) => {
  const change = (i - 50) / 100;
  return { change, ends_beyond: Math.abs(change) === 0.05 ? 0.12 : 0.5, touches: 0.2 };
});
const horizon = (steps: number, low: number, high: number) => ({
  summary: {
    steps,
    quantiles: { "0.05": low - 10, "0.25": 395, "0.5": 404, "0.75": 410, "0.95": high + 10 },
    intervals: [
      { level: 0.5, low: 395, high: 410 },
      { level: 0.8, low, high },
      { level: 0.95, low: low - 15, high: high + 15 },
    ],
    histogram_edges: [],
    histogram_counts: [],
    expected_worst_drawdown: -0.02,
    mean_return: 0.01,
  },
  chances: CHANCES,
  coverage: [
    { level: 0.5, n: 39, inside: 20 },
    { level: 0.8, n: 39, inside: 35 },
    { level: 0.95, n: 39, inside: 38 },
  ],
  baseline_coverage: [{ level: 0.8, n: 39, inside: 34 }],
});
const days = (n: number, end: number) => Array.from({ length: n }, (_, i) => 400 + (end * i) / n);

const ANALYSIS = {
  value: 400,
  covered_value: 400,
  young: [{ symbol: "PURR", name: "Purr (PURR)", weight: 0.05, days: 208 }],
  positions: [
    { symbol: "BTC/USD", name: "Bitcoin", quantity: 0.001, tag: "satellite", weight: 0.1 },
    { symbol: "SPY", name: "US stocks (S&P 500)", quantity: 0.1, tag: null, weight: 0.15 },
    { symbol: "USD", name: "Cash (US dollars)", quantity: 300, tag: null, weight: 0.75 },
  ],
  simulation: {
    model_version: "portfolio-bootstrap-1",
    n_paths: 10000,
    block: 10,
    n_days: 1444,
    start_value: 400,
    scale: 1.11,
    fan: {
      "0.05": days(91, -15),
      "0.25": days(91, -5),
      "0.5": days(91, 6),
      "0.75": days(91, 17),
      "0.95": days(91, 37),
    },
    horizons: [horizon(30, 392, 414), horizon(90, 388, 430)],
  },
  sleeves: {
    sleeves: [
      {
        group: "satellite",
        symbols: ["BTC/USD"],
        weight: 0.1,
        risk_share: 0.7,
        contribution: 0.02,
      },
      { group: "untagged", symbols: ["SPY"], weight: 0.15, risk_share: 0.3, contribution: -0.005 },
      { group: "cash", symbols: ["USD"], weight: 0.75, risk_share: 0, contribution: 0 },
    ],
    n_days: 250,
    first_day: "2025-10-06",
    last_day: "2026-10-05",
    total_return: 0.015,
    short: [],
  },
  trust: {
    xray: { grade: "solid", reason: "Estimated on 1,444 days." },
    simulation: { grade: "solid", reason: "The 80% range held in 35 of 39 past forecasts." },
  },
} as unknown as PortfolioAnalysis;

describe("RangeAheadPanel", () => {
  afterEach(cleanup);

  it("shows the range in money with how often past ranges held", () => {
    const { container } = render(<RangeAheadPanel analysis={ANALYSIS} />);
    expect(
      screen.getByText("8 in 10 simulated futures end between $392.00 and $414.00"),
    ).toBeVisible();
    expect(screen.getByText("$404.00")).toBeVisible(); // the middle outcome
    expect(screen.getByText("-$8.00")).toBeVisible(); // a 2% dip on $400
    expect(screen.getByRole("img", { name: /^Spread of simulated values widening from \$400.00/ }));
    expect(screen.getByText("held 35 of 39")).toBeInTheDocument();
    // A newer holding is not drawn from, and the screen says what was done about it.
    expect(container.textContent).toMatch(/Purr has too short a record/);
    expect(container.textContent).toMatch(/not what will happen/);
    // The simpler method's record is stated beside the simulation's, with no claim to beat it.
    expect(container.textContent).toMatch(
      /Its 80% range held 34 of 39; this one 35 of 39.*not because its range has proved more accurate/,
    );
    expect(container.textContent).not.toMatch(/\b(buy|sell|you should)\b/i);
  });

  it("lets the horizon and the size of change be chosen", () => {
    render(<RangeAheadPanel analysis={ANALYSIS} />);
    // It opens on a fall of 5%.
    expect(screen.getByText("Down 5% or more at the end of 30 trading days")).toBeVisible();
    expect(screen.getByText("12%")).toBeVisible();
    expect(screen.getByText("$380.00")).toBeVisible();

    fireEvent.change(screen.getByLabelText("Change in value, percent"), { target: { value: "8" } });
    expect(screen.getByText("Up 8% or more at any point on the way")).toBeVisible();
    expect(screen.getByText("$432.00")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "90 trading days" }));
    expect(
      screen.getByText("8 in 10 simulated futures end between $388.00 and $430.00"),
    ).toBeVisible();
    expect(screen.getByText("Up 8% or more at the end of 90 trading days")).toBeVisible();
  });

  it("says why there is no range when the holdings share too little history", () => {
    render(<RangeAheadPanel analysis={{ ...ANALYSIS, simulation: null }} />);
    expect(screen.getByText(/A range needs 250 trading days/)).toBeVisible();
  });
});

describe("SleevesPanel", () => {
  beforeEach(() => {
    state.mutate = vi.fn();
  });
  afterEach(cleanup);

  it("sets each group's share of the money beside its share of the risk", () => {
    const { container } = render(<SleevesPanel analysis={ANALYSIS} />);
    expect(
      screen.getByText("Satellite holdings are 10% of your money and 70% of your risk"),
    ).toBeVisible();
    expect(
      screen.getByRole("img", {
        name: "Share of your money: Satellite 10%, Not tagged 15%, Cash 75%",
      }),
    ).toBeVisible();
    expect(
      screen.getByRole("img", {
        name: "Share of your risk: Satellite 70%, Not tagged 30%, Cash 0%",
      }),
    ).toBeVisible();
    expect(screen.getByText("+2.00% · $8.00")).toBeVisible();
    expect(screen.getByText("−0.50% · -$2.00")).toBeVisible();
    expect(container.textContent).toMatch(/not what you earned/);
    expect(container.textContent).not.toMatch(/\b(buy|sell|you should)\b/i);
  });

  it("lets every holding but cash be tagged, one at a time", () => {
    render(<SleevesPanel analysis={ANALYSIS} />);
    const bitcoin = screen.getByRole("group", { name: "Bitcoin is" });
    expect(bitcoin.querySelector('[aria-pressed="true"]')).toHaveTextContent("Satellite");
    expect(screen.queryByRole("group", { name: "Cash is" })).toBeNull();

    const stocks = screen.getByRole("group", { name: "US stocks is" });
    fireEvent.click(stocks.querySelectorAll("button")[0] as HTMLElement);
    expect(state.mutate).toHaveBeenCalledWith({ tags: { SPY: "core" } });
    fireEvent.click(bitcoin.querySelectorAll("button")[2] as HTMLElement);
    expect(state.mutate).toHaveBeenCalledWith({ tags: { "BTC/USD": null } });
  });

  it("asks for tags before there is anything to report", () => {
    render(<SleevesPanel analysis={{ ...ANALYSIS, sleeves: null }} />);
    expect(screen.getByText("Tag your holdings to see what each group carries")).toBeVisible();
    expect(screen.queryByText("Share of your risk")).toBeNull();
  });
});
