import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PortfolioAnalysis } from "../api/client";
import { PlanPanel, STARTS, sharesFor } from "./PlanPanel";

const state = vi.hoisted(() => ({
  save: vi.fn(),
  preview: vi.fn(),
  result: undefined as unknown,
}));
vi.mock("../api/queries", () => ({
  useSetTarget: () => ({ mutate: state.save, isPending: false, isSuccess: false, isError: false }),
  useWhatIf: () => ({ mutate: state.preview, data: state.result }),
  useMixRisk: () => ({ data: { deepest_fall: -0.2 }, isPending: false }),
}));

const position = (symbol: string, name: string, weight: number) => ({
  symbol,
  name,
  weight,
  value: weight * 400,
  quantity: 1,
  price: 1,
  tag: null,
});
const ANALYSIS = {
  value: 400,
  positions: [
    position("BTC/USD", "Bitcoin", 0.08),
    position("PAXG/USD", "PAX Gold", 0.03),
    position("PURR", "PURR", 0.01),
    position("SPY", "US stocks (S&P 500)", 0.11),
    position("USD", "Cash (US dollars)", 0.77),
  ],
  plan: null,
} as unknown as PortfolioAnalysis;

const KINDS = { "BTC/USD": "bitcoin", "PAXG/USD": "gold", SPY: "stocks", GLD: "gold" };

const show = () =>
  render(
    <MemoryRouter>
      <PlanPanel analysis={ANALYSIS} kinds={KINDS} />
    </MemoryRouter>,
  );

describe("PlanPanel", () => {
  beforeEach(() => {
    state.save = vi.fn();
    state.preview = vi.fn();
    state.result = undefined;
  });
  afterEach(cleanup);

  it("starts from the account as it is, with cash as whatever is left", () => {
    const { container } = show();
    expect(screen.getByRole("slider", { name: "Bitcoin share" })).toHaveValue("8");
    expect(container.textContent).toMatch(/Cash.*whatever is left.*77%/);
    expect(container.textContent).toMatch(/small bet, 1% at most/);
  });

  it("fills in a starting point with one tap and saves the shares as the plan", () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: /Careful/ }));
    expect(screen.getByRole("slider", { name: "US stocks share" })).toHaveValue("25");
    expect(screen.getByRole("slider", { name: "PAX Gold share" })).toHaveValue("20");
    expect(screen.getByRole("slider", { name: "Bitcoin share" })).toHaveValue("7");
    fireEvent.click(screen.getByRole("button", { name: "Save as my plan" }));
    expect(state.save.mock.calls[0]?.[0]).toEqual({
      weights: { "BTC/USD": 0.07, "PAXG/USD": 0.2, PURR: 0.01, SPY: 0.25 },
    });
  });

  it("never lets the shares pass the whole account, or a small bet pass its cap", () => {
    show();
    fireEvent.change(screen.getByRole("slider", { name: "US stocks share" }), {
      target: { value: "100" },
    });
    // 8 + 3 + 1 are taken by the others, so stocks stops at 88 and cash at nothing.
    expect(screen.getByRole("slider", { name: "US stocks share" })).toHaveValue("88");
    expect(screen.getByRole("slider", { name: "PURR share" })).toHaveAttribute("max", "1");
  });

  it("shows what the mix would have done, in money and in plain words", () => {
    state.result = { daily_volatility: 0.005, deepest_fall: -0.16, level: "low" };
    const { container } = show();
    expect(container.textContent).toMatch(/A usual day±\$2\.00/);
    expect(container.textContent).toMatch(/Worst fall so far−16%/);
    expect(container.textContent).not.toMatch(/\b(you should|buy now|sell now)\b/i);
  });

  it("turns a starting point into shares for what is really held", () => {
    const careful = STARTS[0];
    expect(sharesFor(careful, ["SPY", "GLD", "BTC/USD", "DOGE"], { DOGE: 5 }, KINDS)).toEqual({
      SPY: 25,
      GLD: 20,
      "BTC/USD": 7,
      DOGE: 1,
    });
    // Gold held two ways shares gold's part between them.
    expect(sharesFor(careful, ["GLD", "PAXG/USD"], {}, KINDS)).toEqual({
      GLD: 10,
      "PAXG/USD": 10,
    });
  });

  it("shows how far each starting point fell on these holdings, not a fixed figure", () => {
    show();
    expect(screen.getAllByText("fell up to 20%")).toHaveLength(3);
  });
});
