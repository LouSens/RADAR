import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { AccountRecord } from "../api/client";
import { RecordPanel, overall, placeWords } from "./RecordPanel";

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

  it("shows gain taken, gain open, trading against holding and fees, in money", () => {
    render(<RecordPanel record={RECORD} />);
    expect(screen.getByText(/24 trades since 1 Jan 2025/)).toBeInTheDocument();
    expect(screen.getAllByText("+$30.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("−$20.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("+$40.00").length).toBeGreaterThan(0);
    expect(screen.getByText("−$1.50")).toBeInTheDocument();
  });

  it("puts into words when the purchases and the sales were made", () => {
    const { container } = render(<RecordPanel record={RECORD} />);
    expect(container.textContent).toMatch(
      /purchases were made in the upper part of the week's range, after a day that had moved \+3\.0%/,
    );
    expect(container.textContent).toMatch(/sales were made in the lower part of the week's range/);
    expect(
      screen.getByRole("img", {
        name: "Purchases: 80% of the way from the week's low to its high",
      }),
    ).toBeInTheDocument();
  });

  it("names a habit only where it is beyond chance, and leaves out barely traded assets", () => {
    const { container } = render(<RecordPanel record={RECORD} />);
    expect(screen.getByText(/Bought in the upper part of the week's range/)).toBeInTheDocument();
    expect(screen.queryByText(/^Sold in the lower part/)).toBeNull();
    expect(screen.getByRole("heading", { name: "SOL" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "DUST" })).toBeNull();
    expect(container.textContent).not.toMatch(/\b(you should|buy now|sell now)\b/i);
  });

  it("weights the overall figure by the money in each asset's trades", () => {
    const assets = [asset("A"), asset("B", { buys: habit(0.4, 0, 100) })];
    expect(overall(assets, "buys", (h) => h.place)).toBeCloseTo((0.8 * 300 + 0.4 * 100) / 400);
    expect(overall([asset("C", { buys: null })], "buys", (h) => h.place)).toBeUndefined();
    expect(placeWords(0.5)).toBe("around the middle of the week's range");
  });
});
