import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Asset, Calendar } from "../api/client";
import { CalendarPage, daysAway, sizeLine, when } from "./CalendarPage";

const state = vi.hoisted(() => ({ calendar: undefined as unknown }));

const ASSETS = [
  { symbol: "GLD", slug: "gld", name: "Gold", asset_class: "stock", is_primary: true },
  {
    symbol: "SPY",
    slug: "spy",
    name: "US stocks (S&P 500)",
    asset_class: "stock",
    is_primary: true,
  },
] as unknown as Asset[];

vi.mock("../api/queries", () => ({
  useAssets: () => ({ data: ASSETS }),
  useCalendar: () => ({ data: state.calendar, isPending: false, isError: false }),
}));

const share = (value: number, verdict = "no measurable pattern") => ({
  n: 85,
  share: value,
  low: value - 0.1,
  high: value + 0.1,
  baseline: 0.54,
  p_value: 0.5,
  verdict,
});
const market = (symbol: string, onEvent: number, verdict: string) => ({
  symbol,
  n_events: 85,
  first_day: "2016-01-27",
  last_day: "2026-09-16",
  size: { n: 85, on_event: onEvent, other_days: 0.0073, p_value: 0.001, verdict },
  day_before: share(0.55),
  event_day: share(0.6),
  next_day: share(0.51),
  next_week: share(0.42),
});

const far = (days: number) => new Date(Date.now() + days * 86_400_000).toISOString();
const CALENDAR = {
  upcoming: [
    { key: "inflation", name: "US inflation report", at: far(8), days_until: 8 },
    { key: "fed", name: "Fed interest rate decision", at: far(22), days_until: 22 },
  ],
  results: [
    {
      key: "fed",
      name: "Fed interest rate decision",
      markets: [
        market("GLD", 0.0092, "moves more on these days"),
        market("SPY", 0.0077, "no measurable difference"),
      ],
    },
    {
      key: "inflation",
      name: "US inflation report",
      markets: [market("GLD", 0.0073, "no measurable difference")],
    },
  ],
  names: { GLD: "Gold", SPY: "US stocks (S&P 500)" },
  direction_tests: 36,
  size_tests: 9,
  trust: {
    fed: { grade: "fair", reason: "Measured on 46 to 85 past events per market." },
    inflation: { grade: "fair", reason: "Measured on 68 to 126 past events per market." },
  },
  computed_at: "2026-10-06T10:38:36Z",
} as unknown as Calendar;

function page(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="calendar/:event?" element={<CalendarPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("CalendarPage", () => {
  beforeEach(() => {
    state.calendar = CALENDAR;
  });
  afterEach(cleanup);

  it("lists what is coming, soonest first, each with what past ones have shown", () => {
    const { container } = page("/calendar");
    expect(screen.getByText("US inflation report: in 8 days")).toBeVisible();
    const fed = screen.getByRole("link", { name: /^Fed interest rate decision/ });
    expect(fed).toHaveAttribute("href", "/calendar/fed");
    expect(within(fed).getByText("Gold moved more than usual on these days")).toBeVisible();
    expect(within(fed).getByText("In 22 days")).toBeVisible();
    const inflation = screen.getByRole("link", { name: /^US inflation report/ });
    expect(
      within(inflation).getByText("No market has moved measurably more on these days"),
    ).toBeVisible();
    expect(container.textContent).toMatch(/does not know what figure is expected/);
  });

  it("shows how each market behaved around one kind of event, against any day", () => {
    const { container } = page("/calendar/fed");
    expect(screen.getByText("Gold moved more than usual on these days")).toBeVisible();
    expect(screen.getByText(/No pattern in direction was found/)).toBeVisible();
    expect(screen.getAllByText(/85 past events, 27 Jan 2016 to 16 Sept? 2026/)).toHaveLength(2);
    expect(screen.getByText("±0.92%")).toBeVisible();
    expect(screen.getAllByText("±0.73%")).toHaveLength(2);
    expect(screen.getByText("Moves more on these days")).toBeVisible();
    expect(screen.getByText("Moves about as much as any day")).toBeVisible();
    expect(
      screen.getAllByRole("img", {
        name: "Ended higher on the day: 60%, plausibly between 50% and 70%; 54% on any day",
      }),
    ).toHaveLength(2);
    expect(screen.getAllByText("No pattern")).toHaveLength(8);
    expect(container.textContent).toMatch(/before any result was computed/);
    expect(container.textContent).toMatch(/36 comparisons of direction and 9 of size/);
    expect(container.textContent).not.toMatch(/\b(buy|sell|you should)\b/i);
  });

  it("says so when a pattern in direction is found", () => {
    const leaning = structuredClone(CALENDAR) as unknown as {
      results: { markets: { event_day: unknown }[] }[];
    };
    const first = leaning.results[0]?.markets[0];
    if (first) first.event_day = share(0.75, "leans up");
    state.calendar = leaning;
    page("/calendar/fed");
    expect(screen.getByText(/A pattern in direction was found/)).toBeVisible();
    expect(screen.getByText("More often up")).toBeVisible();
  });

  it("handles an unknown address and a calendar not yet worked out", () => {
    page("/calendar/elections");
    expect(screen.getByText("Coming up", { selector: "h2" })).toBeVisible();
    cleanup();
    state.calendar = null;
    page("/calendar");
    expect(screen.getByText("The calendar has not been worked out yet.")).toBeVisible();
  });
});

describe("calendar helpers", () => {
  it("counts days in the viewer's own calendar and words them", () => {
    const now = new Date(2026, 9, 6, 23, 30);
    expect(daysAway(new Date(2026, 9, 7, 0, 30).toISOString(), now)).toBe(1);
    expect(daysAway(new Date(2026, 9, 6, 23, 45).toISOString(), now)).toBe(0);
    expect(daysAway(new Date(2026, 9, 14, 20, 30).toISOString(), now)).toBe(8);
    expect([when(0), when(1), when(8)]).toEqual(["Today", "Tomorrow", "In 8 days"]);
  });

  it("names every market that moves more", () => {
    const both = {
      key: "fed",
      name: "Fed",
      markets: [
        market("GLD", 0.01, "moves more on these days"),
        market("SPY", 0.01, "moves more on these days"),
      ],
    } as unknown as Calendar["results"][number];
    expect(sizeLine(both, { GLD: "Gold", SPY: "US stocks (S&P 500)" })).toBe(
      "Gold and US stocks moved more than usual on these days",
    );
  });
});
