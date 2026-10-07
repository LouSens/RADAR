import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Asset, Risk, RiskMethod, Volatility } from "../api/client";
import { oddsLabel, RiskPanel } from "./RiskPanel";
import { linePaths, VolatilityPanel } from "./VolatilityPanel";

const state = vi.hoisted(() => ({
  volatility: null as unknown,
  risk: null as unknown,
  newsTest: null as unknown,
}));
vi.mock("../api/queries", () => ({
  useVolatility: () => ({ data: state.volatility }),
  useNewsTest: () => ({ data: state.newsTest }),
  useRisk: () => ({ data: state.risk }),
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

const VOLATILITY: Volatility = {
  symbol: "GLD",
  as_of: "2026-10-02T20:00:00Z",
  model_version: "volatility-har-1",
  horizons: [
    {
      horizon_days: 1,
      steps: 1,
      shown: "har",
      reason: "trees_did_not_beat_har",
      forecast: 0.0124,
      last_realised: 0.01,
      history: [
        { ts: "2026-09-30T20:00:00Z", forecast: 0.011, realised: 0.012 },
        { ts: "2026-10-01T20:00:00Z", forecast: 0.012, realised: 0.01 },
        { ts: "2026-10-02T20:00:00Z", forecast: 0.0124, realised: null },
      ],
      n: 2201,
      first_day: "2017-12-28",
      last_day: "2026-10-01",
      scores: [
        { model: "har", qlike: 0.667, mse: 3e-5, dm_p_value_vs_har: null },
        { model: "gbt", qlike: 0.872, mse: 3.2e-5, dm_p_value_vs_har: 0.0 },
        { model: "carry", qlike: 1.822, mse: 4.8e-5, dm_p_value_vs_har: 0.0 },
        { model: "regime", qlike: 0.659, mse: 3.4e-5, dm_p_value_vs_har: 0.647 },
      ],
    },
  ],
};

function method(name: string, values: Partial<RiskMethod>): RiskMethod {
  return {
    method: name,
    var: 0.02,
    expected_shortfall: 0.028,
    n: 1951,
    breaches: 106,
    expected_breaches: 97.55,
    breach_rate: 0.054,
    kupiec_p_value: 0.39,
    clustering_p_value: 0.18,
    reliable: true,
    ...values,
  };
}

const RISK: Risk = {
  symbol: "GLD",
  as_of: "2026-10-02T20:00:00Z",
  model_version: "tail-risk-1",
  horizons: [
    {
      horizon_days: 1,
      steps: 1,
      shown: "filtered",
      first_day: "2019-01-02",
      last_day: "2026-10-01",
      levels: [
        {
          level: 0.95,
          methods: [
            method("historical", { var: 0.017, breaches: 130, reliable: false }),
            method("filtered", {}),
          ],
        },
        {
          level: 0.99,
          methods: [
            method("filtered", {
              var: 0.034,
              expected_shortfall: 0.041,
              breaches: 31,
              expected_breaches: 19.51,
              reliable: false,
            }),
          ],
        },
      ],
    },
  ],
  drawdowns: [
    { peak_day: "2020-08-06", trough_day: "2022-09-26", depth: -0.22, recovered_day: "2023-12-01" },
    { peak_day: "2026-01-29", trough_day: "2026-07-16", depth: -0.264, recovered_day: null },
  ],
};

describe("VolatilityPanel", () => {
  afterEach(cleanup);
  beforeEach(() => {
    state.volatility = VOLATILITY;
    state.newsTest = null;
  });

  it("says plainly when news did not improve the forecast, with both errors shown", () => {
    const pair = (family: "har" | "gbt", without: number, withNews: number, helps: boolean) => ({
      family,
      qlike_without: without,
      qlike_with: withNews,
      improvement: (without - withNews) / without,
      dm_statistic: -1,
      dm_p_value: helps ? 0.001 : 0.4,
      dm_p_adjusted: helps ? 0.01 : 0.7,
      verdict: helps ? ("news helps" as const) : ("no measurable gain" as const),
    });
    const horizon = (days: number, helps: boolean) => ({
      steps: days === 1 ? 1 : 5,
      horizon_days: days,
      n: 668,
      first_day: "2024-02-02",
      last_day: "2026-10-01",
      pairs: [pair("har", 0.728, helps ? 0.6 : 0.731, helps), pair("gbt", 1.002, 1.021, false)],
    });
    state.newsTest = {
      symbol: "GLD",
      model_version: "news-volatility-1",
      comparisons: 12,
      horizons: [horizon(1, false)],
      news_helps: false,
    };
    render(<VolatilityPanel asset={GOLD} />);
    expect(screen.getByText("Does news improve this forecast?")).toBeInTheDocument();
    expect(screen.getByText("No measurable gain")).toBeInTheDocument();
    expect(screen.getByText("0.728")).toBeInTheDocument();
    expect(screen.getByText("0.731")).toBeInTheDocument();
    expect(screen.getByText(/Error higher by 0.4%, within chance/)).toBeInTheDocument();
    expect(screen.getByText(/before the test was run/)).toBeInTheDocument();
    expect(screen.getByText(/12 comparisons across all markets/)).toBeInTheDocument();
    // When the rule is met for the horizon in view, it says so.
    cleanup();
    state.newsTest = {
      symbol: "GLD",
      model_version: "news-volatility-1",
      comparisons: 12,
      horizons: [horizon(1, true)],
      news_helps: true,
    };
    render(<VolatilityPanel asset={GOLD} />);
    expect(screen.getByText("Yes, measurably")).toBeInTheDocument();
    expect(screen.getByText(/Error lower by 17.6%, more than chance/)).toBeInTheDocument();
  });

  it("shows nothing until a forecast is stored", () => {
    state.volatility = null;
    expect(render(<VolatilityPanel asset={GOLD} />).container).toBeEmptyDOMElement();
  });

  it("shows the forecast beside the last realised value, without a direction", () => {
    render(<VolatilityPanel asset={GOLD} />);
    expect(
      screen.getByText("Typical daily move expected over the next 1 trading day"),
    ).toBeInTheDocument();
    expect(screen.getByText("±1.24%")).toBeInTheDocument();
    expect(screen.getByText("±1.00%")).toBeInTheDocument();
    expect(screen.getByText("+24.00%")).toBeInTheDocument();
    expect(screen.getByText(/says nothing about which direction/)).toBeInTheDocument();
  });

  it("states which method is shown and how the others compare", () => {
    render(<VolatilityPanel asset={GOLD} />);
    expect(screen.getByText("Shown")).toBeInTheDocument();
    expect(screen.getAllByText("Measurably worse")).toHaveLength(2);
    // The state average scored slightly lower, but not by a measurable margin.
    expect(screen.getByText("No measurable difference")).toBeInTheDocument();
    expect(screen.getByText(/Scored on 2,201 days/)).toBeInTheDocument();
    expect(screen.getByText(/so the simpler one is shown/)).toBeInTheDocument();
  });

  it("falls back to the first period when the chosen one is not stored", () => {
    render(<VolatilityPanel asset={GOLD} />);
    fireEvent.click(screen.getByRole("button", { name: "1 week" }));
    expect(screen.getByText("±1.24%")).toBeInTheDocument();
  });

  it("draws the outcome line only where the outcome is known", () => {
    const paths = linePaths(VOLATILITY.horizons[0]?.history ?? [], 200, 100);
    expect(paths?.high).toBe(0.0124);
    expect(paths?.forecast.split(/[ML]/).filter(Boolean)).toHaveLength(3);
    expect(paths?.realised.split(/[ML]/).filter(Boolean)).toHaveLength(2);
    expect(linePaths([], 200, 100)).toBeUndefined();
  });
});

describe("RiskPanel", () => {
  afterEach(cleanup);
  beforeEach(() => {
    state.risk = RISK;
  });

  it("shows nothing until risk figures are stored", () => {
    state.risk = null;
    expect(render(<RiskPanel asset={GOLD} />).container).toBeEmptyDOMElement();
  });

  it("shows each limit from the best method, with breaches against expected", () => {
    render(<RiskPanel asset={GOLD} />);
    expect(screen.getByText("A bad day (about 1 in 20)")).toBeInTheDocument();
    expect(screen.getByText("A very bad day (about 1 in 100)")).toBeInTheDocument();
    expect(screen.getAllByText("2.0%").length).toBeGreaterThan(0);
    expect(screen.getByText("98")).toBeInTheDocument(); // 97.55 expected breaches at 95%
    expect(screen.getByText("Past losses scaled to expected swings")).toBeInTheDocument();
    expect(screen.getByText("(shown)")).toBeInTheDocument();
  });

  it("marks a limit that failed its coverage test as unreliable", () => {
    render(<RiskPanel asset={GOLD} />);
    // Only the 99% limit of the shown method failed; the 95% one held.
    expect(screen.getAllByText(/Treat it as rough/)).toHaveLength(1);
    expect(screen.getByText(/130 of 1,951, unreliable/)).toBeInTheDocument();
  });

  it("lists the deepest falls with their dates", () => {
    render(<RiskPanel asset={GOLD} />);
    expect(screen.getByText("-26.4%")).toBeInTheDocument();
    expect(screen.getByText(/not yet recovered/)).toBeInTheDocument();
    expect(screen.getByText(/recovered by/)).toBeInTheDocument();
  });

  it("names odds in plain terms", () => {
    expect(oddsLabel(0.95)).toBe("19 in 20");
    expect(oddsLabel(0.99)).toBe("99 in 100");
  });

  it("never tells the reader what to do", () => {
    const { container } = render(
      <>
        <RiskPanel asset={GOLD} />
        <VolatilityPanel asset={GOLD} />
      </>,
    );
    expect(container.textContent).not.toMatch(/\b(buy|sell|you should)\b/i);
  });
});
