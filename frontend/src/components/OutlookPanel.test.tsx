import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Asset, Calibration, LevelAnswer, Simulation } from "../api/client";
import { OutlookPanel } from "./OutlookPanel";

const state = vi.hoisted(() => ({
  simulation: null as unknown,
  calibration: null as unknown,
  level: {
    data: undefined as unknown,
    isPending: false,
    isError: false,
    mutate: vi.fn(),
  },
}));
vi.mock("../api/queries", () => ({
  useSimulation: () => ({ data: state.simulation }),
  useCalibration: () => ({ data: state.calibration }),
  useLevel: () => state.level,
}));

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

function horizon(days: number, steps: number, widest = false): Simulation["horizons"][number] {
  return {
    horizon_days: days,
    steps,
    quantiles: {
      "0.05": 340,
      "0.25": 352,
      "0.5": 358,
      "0.75": 364,
      "0.95": 376,
    },
    intervals: [
      {
        level: 0.5,
        low: 352,
        high: 364,
        adjusted_low: 351,
        adjusted_high: 365,
        adjusted_is_widest: false,
      },
      {
        level: 0.8,
        low: 345,
        high: 371,
        adjusted_low: 344,
        adjusted_high: 372,
        adjusted_is_widest: false,
      },
      {
        level: 0.95,
        low: 336,
        high: 380,
        adjusted_low: 320,
        adjusted_high: 396,
        adjusted_is_widest: widest,
      },
    ],
    histogram_edges: [330, 345, 360, 375, 390],
    histogram_counts: [500, 4500, 4400, 600],
    expected_worst_drawdown: -0.021,
    mean_return: 0.004,
  };
}

const SIMULATION: Simulation = {
  symbol: "GLD",
  as_of: "2026-10-02T20:00:00Z",
  start_price: 357,
  n_paths: 10000,
  seed: 588099749,
  model_version: "simulator-rsmc-1",
  horizons: [horizon(1, 1), horizon(7, 5), horizon(30, 21, true)],
  fan: {
    "0.05": [357, 352, 349, 346, 344, 342],
    "0.25": [357, 355, 354, 353, 352, 352],
    "0.5": [357, 357, 358, 358, 358, 358],
    "0.75": [357, 360, 361, 362, 363, 364],
    "0.95": [357, 363, 366, 369, 372, 376],
  },
};

const CALIBRATION: Calibration = {
  symbol: "GLD",
  model_version: "simulator-rsmc-1",
  computed_at: "2026-10-05T15:22:04Z",
  rows: [0.5, 0.8, 0.95].map((nominal) => ({
    horizon_days: 7,
    steps: 5,
    nominal,
    empirical: nominal - 0.01,
    empirical_conformal: nominal + 0.001,
    n: 2197,
    pinball_model: 0.00489,
    pinball_baseline: 0.00486,
    first_origin: "2018-01-03",
    last_origin: "2026-09-25",
  })),
};

describe("OutlookPanel", () => {
  afterEach(cleanup);

  beforeEach(() => {
    state.simulation = SIMULATION;
    state.calibration = CALIBRATION;
    state.level = {
      data: undefined,
      isPending: false,
      isError: false,
      mutate: vi.fn(),
    };
  });

  it("shows nothing until a simulation is stored", () => {
    state.simulation = null;
    const { container } = render(<OutlookPanel asset={GOLD} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the adjusted 80% range for a week, counted in trading days", () => {
    render(<OutlookPanel asset={GOLD} />);
    expect(screen.getByText("80% of simulated outcomes after 5 trading days")).toBeInTheDocument();
    expect(screen.getByText("$344.00 to $372.00")).toBeInTheDocument();
    expect(screen.getByText(/Ranges shown are adjusted/)).toBeInTheDocument();
    expect(screen.getByText(/not a prediction/)).toBeInTheDocument();
  });

  it("shows how past ranges held, with the sample size and the baseline comparison", () => {
    render(<OutlookPanel asset={GOLD} />);
    expect(screen.getByText("How past ranges held")).toBeInTheDocument();
    expect(screen.getAllByText("2,197")).toHaveLength(3);
    expect(screen.getByText("79.0%")).toBeInTheDocument();
    expect(screen.getByText("80.1%")).toBeInTheDocument();
    // 0.00489 against 0.00486 is 0.6% higher: the panel says so plainly.
    expect(screen.getByText(/0\.6% higher than a simple forecast/)).toBeInTheDocument();
    expect(screen.getByText(/adds nothing over that simple forecast/)).toBeInTheDocument();
  });

  it("says when a range has been widened as far as it can go", () => {
    render(<OutlookPanel asset={GOLD} />);
    expect(screen.queryByText(/widened as far as it can go/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "1 month" }));
    expect(screen.getByText("80% of simulated outcomes after 21 trading days")).toBeInTheDocument();
    expect(
      screen.getByText(/The 95% range has been widened as far as it can go/),
    ).toBeInTheDocument();
    // No track record is stored for this period in the fixture, so none is shown.
    expect(screen.queryByText("How past ranges held")).toBeNull();
  });

  it("asks for a level and keeps ending beyond it apart from reaching it", () => {
    const { rerender } = render(<OutlookPanel asset={GOLD} />);
    const input = screen.getByLabelText("Price in US dollars");
    fireEvent.change(input, { target: { value: "370" } });
    fireEvent.click(screen.getByRole("button", { name: "Check" }));
    expect(state.level.mutate).toHaveBeenCalledWith({
      level: 370,
      horizon_days: 7,
    });

    const answer: LevelAnswer = {
      symbol: "GLD",
      as_of: SIMULATION.as_of,
      start_price: 357,
      level: 370,
      horizon_days: 7,
      steps: 5,
      n_paths: 10000,
      ends_above: 0.112,
      ends_below: 0.888,
      touches: 0.187,
    };
    state.level = { ...state.level, data: answer };
    rerender(<OutlookPanel asset={GOLD} />);
    expect(screen.getByText("Ends at or above $370.00")).toBeInTheDocument();
    expect(screen.getByText("11.2%")).toBeInTheDocument();
    expect(screen.getByText("Reaches $370.00 at any daily close")).toBeInTheDocument();
    expect(screen.getByText("18.7%")).toBeInTheDocument();

    // An answer for another level is not shown against a new entry.
    fireEvent.change(input, { target: { value: "340" } });
    expect(screen.queryByText("18.7%")).toBeNull();
  });

  it("never tells the reader what to do", () => {
    const { container } = render(<OutlookPanel asset={GOLD} />);
    expect(container.textContent).not.toMatch(/\b(buy|sell|you should)\b/i);
  });
});
