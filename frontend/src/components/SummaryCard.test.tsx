import { cleanup, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import type { Asset, Summary } from "../api/client";
import { SummaryCard } from "./SummaryCard";

const GOLD: Asset = {
  symbol: "GLD",
  slug: "gld",
  name: "Gold",
  asset_class: "stock",
  is_primary: true,
  history_start: "2016-01-04",
  news_start: "2023-01-01",
  trades_continuously: false,
};

const trust = (grade: "solid" | "fair" | "rough", reason: string) => ({ grade, reason });

const SUMMARY: Summary = {
  symbol: "GLD",
  state: { label: "turbulent", probability: 0.93, days_in_state: 3 },
  outlook: { horizon_days: 7, steps: 5, level: 0.8, low: 344, high: 372, start_price: 357 },
  swings: { forecast: 0.0133, last_realised: 0.0125 },
  risk: { horizon_days: 1, level: 0.95, limit: 0.027 },
  news: { current: 0.04, articles_24h: 3, verdict: "no measurable relationship" },
  changes: [
    { topic: "state", text: "The market state changed to turbulent 3 days ago." },
    { topic: "swings", text: "Expected daily swings are 22% larger than a week ago." },
  ],
  trust: {
    state: trust("solid", "On 2,202 unseen days, rougher states were followed by larger swings."),
    outlook: trust("fair", "A simple forecast was a little more accurate."),
    swings: trust("solid", "On 2,201 unseen days it beat both simple forecasts."),
    risk: trust("solid", "Over 1,951 past periods the limits held as stated."),
    news: trust("rough", "It agreed with labels on 61% of 700 headlines."),
  },
};

const routed = (ui: ReactElement) => <MemoryRouter>{ui}</MemoryRouter>;

describe("SummaryCard", () => {
  afterEach(cleanup);

  it("states each answer in a sentence, counting market sessions for a stock", () => {
    render(routed(<SummaryCard asset={GOLD} summary={SUMMARY} />));
    expect(screen.getByText("turbulent")).toBeVisible();
    expect(screen.getByText("3 days")).toBeVisible();
    expect(screen.getByText(/Over the next 5 market sessions, 8 in 10 simulated/)).toBeVisible();
    expect(screen.getByText("$344.00 and $372.00")).toBeVisible();
    expect(screen.getByText("±1.33%")).toBeVisible();
    expect(screen.getByText("2.7%")).toBeVisible();
    expect(screen.getByText("mixed")).toBeVisible();
    expect(screen.getByText(/no measurable link to later price moves/)).toBeVisible();
  });

  it("puts a trust grade and a link to the evidence beside every statement", () => {
    render(routed(<SummaryCard asset={GOLD} summary={SUMMARY} />));
    expect(screen.getAllByText("Solid")).toHaveLength(3);
    expect(screen.getByText("Fair")).toBeVisible();
    expect(screen.getByText("Rough")).toBeVisible();
    expect(screen.getByText("Rough")).toHaveAttribute(
      "title",
      "It agreed with labels on 61% of 700 headlines.",
    );
    const links = screen.getAllByRole("link", { name: "Evidence" });
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/asset/gld/state",
      "/asset/gld/outlook",
      "/asset/gld/swings",
      "/asset/gld/risk",
      "/asset/gld/news",
    ]);
  });

  it("lists what changed this week, or says nothing did", () => {
    const { rerender } = render(routed(<SummaryCard asset={GOLD} summary={SUMMARY} />));
    expect(screen.getByText("Expected daily swings are 22% larger than a week ago.")).toBeVisible();
    rerender(routed(<SummaryCard asset={GOLD} summary={{ ...SUMMARY, changes: [] }} />));
    expect(screen.getByText("Nothing notable has changed in the past week.")).toBeVisible();
  });

  it("leaves out what is not stored and shows nothing when there is nothing at all", () => {
    const { container, rerender } = render(
      routed(<SummaryCard asset={GOLD} summary={{ ...SUMMARY, news: null, risk: null }} />),
    );
    expect(screen.queryByText(/Recent news is/)).toBeNull();
    expect(screen.getAllByRole("link", { name: "Evidence" })).toHaveLength(3);
    rerender(
      routed(
        <SummaryCard
          asset={GOLD}
          summary={{ ...SUMMARY, state: null, outlook: null, swings: null, risk: null, news: null }}
        />,
      ),
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("never tells the reader what to do", () => {
    const { container } = render(routed(<SummaryCard asset={GOLD} summary={SUMMARY} />));
    expect(container.textContent).not.toMatch(/\b(buy|sell|you should)\b/i);
  });
});
