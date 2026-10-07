import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { BuyCheck } from "../api/client";
import { CheckResult } from "./CheckPanel";

const CHECK: BuyCheck = {
  coin: "SOL",
  as_of: "2026-10-07T09:00:00Z",
  model_version: "check-1",
  price: 118.8,
  place_day: 0.5,
  place_week: 0.92,
  place_year: 0.3,
  place_month: 0.8,
  place_quarter: 0.4,
  move_day: 0.031,
  move_week: 0.084,
  below_high: -0.21,
  weekly_swing: 0.09,
  where: "high",
  yours: { purchases: 27, sales: 15, result: -28.8, held: false },
  habit_place: 0.63,
  outcomes: [
    { where: "high", trades: 140, after_week: -0.021, fell_share: 0.61 },
    { where: "low", trades: 60, after_week: 0.004, fell_share: 0.48 },
    { where: "middle", trades: 3, after_week: 0.2, fell_share: 0 },
  ],
};

describe("CheckResult", () => {
  afterEach(cleanup);

  it("says in plain words whether the price is high or low, with the three periods", () => {
    const { container } = render(<CheckResult check={CHECK} />);
    expect(screen.getByText("The price is high right now")).toBeInTheDocument();
    expect(container.textContent).toMatch(
      /is up 3\.1% since yesterday and is up 8\.4% over the week/,
    );
    expect(container.textContent).toMatch(/21\.0% below its highest price of the last 3 months/);
    expect(
      screen.getByRole("img", {
        name: "This week: 92 out of 100, where 0 is the lowest price and 100 the highest",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("This month")).toBeInTheDocument();
    expect(screen.getByText("Last 3 months")).toBeInTheDocument();
    expect(screen.getByText("Today")).toBeInTheDocument();
    expect(screen.getByText("Last year")).toBeInTheDocument();
  });

  it("sets your own record beside it, leaving out groups with too few purchases", () => {
    const { container } = render(<CheckResult check={CHECK} />);
    expect(container.textContent).toMatch(/you usually bought at 63 out of 100 in the week/);
    expect(container.textContent).toMatch(
      /When you bought near the week's top \(140 times\): a week later the price was down 2\.1% on average, and lower 61 times out of 100/,
    );
    expect(container.textContent).toMatch(/near the week's bottom \(60 times\)/);
    expect(container.textContent).not.toMatch(/around the middle \(3 times\)/);
    expect(container.textContent).toMatch(
      /you bought it 27 times and sold it 15, and are −\$28\.80 on it/,
    );
    expect(container.textContent).not.toMatch(/\b(you should|buy now|sell now)\b/i);
  });

  it("reads low and middle the same way, and copes with a coin you never traded", () => {
    render(
      <CheckResult
        check={{ ...CHECK, where: "low", yours: null, habit_place: null, outcomes: [] }}
      />,
    );
    expect(screen.getByText("The price is low right now")).toBeInTheDocument();
    expect(screen.queryByText("Your own record")).toBeNull();
  });
});
