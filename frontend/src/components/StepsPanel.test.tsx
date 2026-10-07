import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import type { Steps } from "../api/client";
import { StepsCard, StepsPanel, placeWords } from "./StepsPanel";

const STEPS: Steps = {
  as_of: "2026-10-07T09:00:00Z",
  model_version: "steps-1",
  has_plan: true,
  value: 400,
  cash: 306,
  cash_plan: 188,
  spare: 118,
  by: "2026-11-06T09:00:00Z",
  steps: [
    {
      symbol: "PAXG/USD",
      name: "PAX Gold",
      kind: "buy",
      amount: 66,
      share_now: 0.03,
      share_plan: 0.2,
      price: 4170,
      place: 0.06,
      below_high: -0.108,
      weekly_swing: 0.022,
      rungs: [
        { price: 4170, amount: 22, below: 0 },
        { price: 4078, amount: 22, below: 0.022 },
        { price: 3987, amount: 22, below: 0.044 },
      ],
      past: { months: 99, average_saving: -0.0047, cheaper_share: 0.47, worst: -0.09 },
    },
    {
      symbol: "BTC/USD",
      name: "Bitcoin",
      kind: "trim",
      amount: 40,
      share_now: 0.17,
      share_plan: 0.07,
      price: 85000,
      place: null,
      below_high: null,
      weekly_swing: null,
      rungs: [],
      past: null,
    },
  ],
};

const show = (node: React.ReactNode) => render(<MemoryRouter>{node}</MemoryRouter>);

describe("StepsPanel", () => {
  afterEach(cleanup);

  it("says how much cash is over the plan and what to buy with it, part by part", () => {
    const { container } = show(<StepsPanel steps={STEPS} />);
    expect(screen.getByText("You have $118.00 more cash than your plan keeps")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Buy $66.00 of PAX Gold" })).toBeInTheDocument();
    expect(container.textContent).toMatch(/Buy \$22\.00 now/);
    expect(container.textContent).toMatch(
      /Buy \$22\.00 if the price falls 2\.2%, to \$4,078 or lower/,
    );
    expect(container.textContent).toMatch(/Whatever is not bought by 6 Nov 2026: buy it that day/);
  });

  it("gives the reasons in plain words, with what buying in steps cost before", () => {
    const { container } = show(<StepsPanel steps={STEPS} />);
    expect(container.textContent).toMatch(/It is 3% of your account now; your plan says 20%/);
    expect(container.textContent).toMatch(
      /Near its lowest price of the last 3 months, 10\.8% below the highest/,
    );
    expect(container.textContent).toMatch(/It usually moves about 2\.2% in a week/);
    expect(container.textContent).toMatch(
      /Over 99 past months it paid 0\.5% more on average than buying all at once, and got a lower price in 47 months out of 100/,
    );
    expect(container.textContent).toMatch(/RADAR cannot tell which way a price goes next/);
  });

  it("lists a holding that has grown past its share, to sell back to it", () => {
    const { container } = show(<StepsPanel steps={STEPS} />);
    expect(screen.getByRole("heading", { name: "Sell $40.00 of Bitcoin" })).toBeInTheDocument();
    expect(container.textContent).toMatch(/grown to 17% of your account; your plan says 7%/);
  });

  it("says so when there is nothing to do, and asks for a plan when there is none", () => {
    show(<StepsPanel steps={{ ...STEPS, steps: [], spare: 2 }} />);
    expect(screen.getByText("Nothing to do right now")).toBeInTheDocument();
    cleanup();
    show(<StepsPanel steps={{ ...STEPS, has_plan: false, steps: [] }} />);
    expect(screen.getByRole("link", { name: "Choose your shares" })).toHaveAttribute(
      "href",
      "/portfolio/try",
    );
  });

  it("puts the same thing in one line on Home, leading to the page", () => {
    show(<StepsCard steps={STEPS} />);
    const card = screen.getByRole("link", { name: "What to do now" });
    expect(card).toHaveAttribute("href", "/portfolio/todo");
    expect(card.textContent).toMatch(/Buy \$66\.00 of PAX Gold · Sell \$40\.00 of Bitcoin/);
    cleanup();
    show(<StepsCard steps={{ ...STEPS, steps: [] }} />);
    expect(screen.getByText("Nothing to do right now")).toBeInTheDocument();
    expect(placeWords(0.5)).toBe("around the middle of its last 3 months");
  });
});
