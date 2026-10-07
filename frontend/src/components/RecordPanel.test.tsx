import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { AccountRecord } from "../api/client";
import { RecordPanel, overall, placeWords, totalOf } from "./RecordPanel";

type AssetRecord = AccountRecord["assets"][number];

const habit = (place: number, before: number, dollars: number) => ({
  trades: 12,
  dollars,
  before_day: before,
  before_week: 0.02,
  place,
  after_day: 0,
  after_week: -0.01,
});

const asset = (name: string, extra: Partial<AssetRecord> = {}): AssetRecord => ({
  asset: name,
  standing: {
    asset: name,
    units: 2,
    cost: 200,
    average_cost: 100,
    realised: 30,
    bought: 500,
    sold: 330,
    fees: 1.5,
    reward_units: 0,
    purchases: 12,
    sales: 12,
    first: "2025-01-01T00:00:00Z",
    priced_at_market: 1,
    unpriced: 0,
  },
  price: 90,
  value: 180,
  unrealised: -20,
  compared: { asset: name, put_in: 300, as_traded: 310, if_held: 270, difference: 40 },
  trips: null,
  buys: habit(0.8, 0.03, 300),
  sells: habit(0.2, -0.04, 100),
  usual: { hours: 5000, before_day: 0, before_week: 0, place: 0.5, after_day: 0, after_week: 0 },
  buys_unusual: true,
  sells_unusual: false,
  held_units: 2,
  missing_share: 0,
  ...extra,
});

const RECORD: AccountRecord = {
  as_of: "2026-10-07T02:00:00Z",
  model_version: "account-1",
  first_trade: "2025-01-01T00:00:00Z",
  trades: 24,
  realised: 30,
  unrealised: -20,
  fees: 1.5,
  put_in: 300,
  as_traded: 310,
  if_held: 270,
  assets: [
    asset("SOL"),
    asset("DUST", { standing: { ...asset("x").standing, purchases: 1, sales: 0 } }),
  ],
  months: [],
  priced_at_market: 1,
};

describe("RecordPanel", () => {
  afterEach(cleanup);

  it("opens with the total in plain words, and how far there is to climb back", () => {
    const { container } = render(<RecordPanel record={{ ...RECORD, realised: -30 }} worth={500} />);
    expect(screen.getByText("You are down $50.00 in total")).toBeInTheDocument();
    expect(container.textContent).toMatch(/From 24 trades since 1 Jan 2025/);
    expect(container.textContent).toMatch(
      /everything you hold \(\$500\.00\) would have to rise 10\.0%/,
    );
    expect(screen.getByText("On coins you sold")).toBeInTheDocument();
    expect(screen.getByText("On coins you still have")).toBeInTheDocument();
    expect(screen.getByText("Fees you paid")).toBeInTheDocument();
    expect(
      screen.getByText("Your selling left you better off than never selling"),
    ).toBeInTheDocument();
  });

  it("says when you usually buy and sell without any jargon", () => {
    const { container } = render(<RecordPanel record={RECORD} />);
    expect(screen.getByText("You are up $10.00 in total")).toBeInTheDocument();
    expect(container.textContent).toMatch(
      /You usually bought near the highest price of that week, when the price had risen 3\.0% in the day before/,
    );
    expect(container.textContent).toMatch(
      /You usually sold near the lowest price of that week, when the price had fallen 4\.0%/,
    );
    expect(container.textContent).toMatch(/Buying nearer the top and selling nearer the bottom/);
    expect(container.textContent).not.toMatch(/chance|realised|unrealised|break-even|weighted/i);
    expect(container.textContent).not.toMatch(/\b(you should|buy now|sell now)\b/i);
  });

  it("lists every coin, biggest loss first, with where each is back to zero", () => {
    render(<RecordPanel record={RECORD} />);
    const names = screen.getAllByRole("heading", { level: 4 }).map((h) => h.textContent);
    expect(names).toEqual(["SOL", "DUST"]);
    expect(screen.getAllByText("You are back to zero at")).toHaveLength(2);
    expect(
      screen.getAllByText(/You usually bought it near the highest price of that week\./),
    ).toHaveLength(2);
    expect(screen.queryByText(/You usually sold it/)).toBeNull();
  });

  it("weights the overall figure by the money in each coin's trades", () => {
    const assets = [asset("A"), asset("B", { buys: habit(0.4, 0, 100) })];
    expect(overall(assets, "buys", (h) => h.place)).toBeCloseTo((0.8 * 300 + 0.4 * 100) / 400);
    expect(overall([asset("C", { buys: null })], "buys", (h) => h.place)).toBeUndefined();
    expect(placeWords(0.5)).toBe("around the middle of that week's prices");
    expect(totalOf(asset("A"))).toBe(10);
  });
});
