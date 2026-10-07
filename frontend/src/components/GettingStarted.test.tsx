import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { Portfolio, PortfolioAnalysis } from "../api/client";
import { GettingStarted, markSeen, steps } from "./GettingStarted";
import { PageSkeleton } from "./Skeleton";

const EMPTY = { holdings: [] } as unknown as Portfolio;
const HELD = { holdings: [{ symbol: "SPY", quantity: 1 }] } as unknown as Portfolio;
const TARGETED = { plan: { target: { level: "low" } } } as unknown as PortfolioAnalysis;

const show = (portfolio: Portfolio | undefined, analysis?: PortfolioAnalysis) =>
  render(
    <MemoryRouter>
      <GettingStarted portfolio={portfolio} analysis={analysis} markets={3} />
    </MemoryRouter>,
  );

describe("GettingStarted", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(cleanup);

  it("starts a newcomer with one step already done and one next step", () => {
    show(EMPTY);
    expect(screen.getByText("1 of 5 done")).toBeVisible();
    expect(screen.getByRole("progressbar", { name: "Steps done" })).toHaveAttribute(
      "aria-valuenow",
      "1",
    );
    expect(screen.getByText("Add what you hold")).toBeVisible();
    // One thing to do, not a list of choices.
    expect(screen.getByRole("link", { name: "Continue" })).toHaveAttribute(
      "href",
      "/portfolio/holdings",
    );
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  it("moves on as each step is really done", () => {
    expect(steps(HELD, undefined, 3).map((s) => s.done)).toEqual([true, true, false, false, false]);
    markSeen("/portfolio/sources");
    markSeen("/portfolio/buying");
    markSeen("/somewhere/else");
    expect(steps(HELD, TARGETED, 3).map((s) => s.done)).toEqual([true, true, true, true, true]);
    // Looking at the risk page does not count while nothing is held.
    expect(steps(EMPTY, undefined, 3).find((s) => s.key === "risk")?.done).toBe(false);
  });

  it("goes away when everything is done, when asked to, and while loading", () => {
    markSeen("/portfolio/sources");
    markSeen("/portfolio/buying");
    const { container } = show(HELD, TARGETED);
    expect(container).toBeEmptyDOMElement();
    cleanup();

    expect(show(undefined).container).toBeEmptyDOMElement();
    cleanup();

    window.localStorage.clear();
    const shown = show(HELD);
    fireEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(shown.container).toBeEmptyDOMElement();
    cleanup();
    expect(show(HELD).container).toBeEmptyDOMElement(); // and it stays away
  });
});

describe("PageSkeleton", () => {
  afterEach(cleanup);

  it("holds the page's shape and tells assistive technology it is loading", () => {
    const { container } = render(<PageSkeleton cards={3} />);
    expect(screen.getByRole("status", { name: "Loading" })).toBeVisible();
    expect(container.querySelectorAll(".glass")).toHaveLength(3);
    expect(container.querySelectorAll(".skeleton").length).toBeGreaterThan(8);
  });
});
