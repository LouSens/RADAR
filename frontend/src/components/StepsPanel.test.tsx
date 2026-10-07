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

  it("says how much cash is spare and draws what to buy as steps down a price line", () => {
    const { container } = show(<StepsPanel steps={STEPS} />);
    expect(screen.getByText("$118.00 of your cash is spare")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Buy $66.00 of PAX Gold" })).toBeInTheDocument();
    expect(
      screen.getByRole("img", {
        name: "Buy $22.00 now at about $4,170; Buy $22.00 at $4,078 or lower; Buy $22.00 at $3,987 or lower",
      }),
    ).toBeInTheDocument();
    expect(container.textContent).toMatch(/Not all bought by 6 Nov 2026\? Buy the rest that day/);
    expect(container.textContent).toMatch(/Steps are 2\.2% apart: a usual week's move/);
  });

  it("shows the reasons as pictures: share against plan, and where the price is", () => {
    const { container } = show(<StepsPanel steps={STEPS} />);
    expect(
      screen.getByRole("img", { name: "3% of your account now; your plan says 20%" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", {
        name: "The price is near its lowest price of the last 3 months",
      }),
    ).toBeInTheDocument();
    expect(container.textContent).toMatch(
      /In 99 past months, buying in steps paid 0\.5% more on average than buying all at once, and got a lower price in 47 of 100 months/,
    );
    expect(container.textContent).toMatch(/RADAR cannot tell which way a price goes next/);
  });

  it("lists a holding that has grown past its share, to sell back to it", () => {
    const { container } = show(<StepsPanel steps={STEPS} />);
    expect(screen.getByRole("heading", { name: "Sell $40.00 of Bitcoin" })).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "17% of your account now; your plan says 7%" }),
    ).toBeInTheDocument();
    expect(container.textContent).toMatch(/brings it back to its share of your plan/);
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

  it("puts the same thing in one card on Home, leading to the page", () => {
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
