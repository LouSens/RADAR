import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Asset, Regime } from "../api/client";
import { RegimePanel } from "./RegimePanel";

const query = vi.hoisted(() => ({ value: {} as unknown }));
vi.mock("../api/queries", () => ({ useRegime: () => query.value }));

const ASSET: Asset = {
  symbol: "BTC/USD",
  slug: "btc-usd",
  name: "Bitcoin",
  asset_class: "crypto",
  is_primary: true,
  history_start: "2021-01-01",
  news_start: "2022-01-01",
  trades_continuously: true,
};

const EVALUATION: NonNullable<Regime["evaluation"]> = {
  n_days: 1602,
  first_test_day: "2022-05-17",
  last_test_day: "2026-10-04",
  next_day_volatility: { calm: 0.0196, normal: 0.0271, turbulent: 0.0363 },
  volatility_is_ordered: true,
  model_log_density: 2.017,
  baseline_log_density: 1.972,
  average_run_length: 34.1,
};

const REGIME: Regime = {
  symbol: "BTC/USD",
  as_of: "2026-10-05T00:00:00Z",
  label: "calm",
  probability: 0.97,
  probabilities: { calm: 0.97, normal: 0.03, turbulent: 0 },
  days_in_state: 12,
  states: [
    { label: "calm", typical_daily_volatility: 0.0145, typical_duration_days: 37, next_states: { normal: 0.98, turbulent: 0.02 } },
    { label: "normal", typical_daily_volatility: 0.0223, typical_duration_days: 20.5, next_states: { calm: 0.56, turbulent: 0.44 } },
    { label: "turbulent", typical_daily_volatility: 0.0358, typical_duration_days: 33.5, next_states: { calm: 0, normal: 1 } },
  ],
  history: [
    { ts: "2026-10-01T00:00:00Z", label: "normal", probability: 0.8 },
    { ts: "2026-10-02T00:00:00Z", label: "calm", probability: 0.9 },
    { ts: "2026-10-05T00:00:00Z", label: "calm", probability: 0.97 },
  ],
  model: {
    version: "regime-hmm-1",
    trained_at: "2026-10-05T11:12:00Z",
    train_start: "2021-01-02",
    train_end: "2026-10-04",
    n_train: 2102,
    bic_by_states: { "2": 9743, "3": 8575, "4": 7687 },
  },
  evaluation: EVALUATION,
};

describe("RegimePanel", () => {
  it("shows the state with its probability, duration, and evidence", () => {
    query.value = { data: REGIME, isPending: false, isError: false };
    const { container } = render(<RegimePanel asset={ASSET} defaultOpen />);
    const text = container.textContent ?? "";
    expect(screen.getAllByText("Calm").length).toBeGreaterThan(0);
    expect(text).toContain("97% probability");
    expect(text).toContain("12 days so far");
    expect(text).toContain("typically lasted 37 days");
    expect(text).toContain("Tested on 1,602 days the model had not seen");
    expect(text).toContain("1.96% after calm, 2.71% after normal, 3.63% after turbulent");
    expect(text).toContain("2,102 days");
    expect(text).not.toMatch(/\b(buy|sell|you should)\b/i);
  });

  it("warns when the test did not order the states", () => {
    query.value = {
      data: { ...REGIME, evaluation: { ...EVALUATION, volatility_is_ordered: false } },
      isPending: false,
      isError: false,
    };
    const { container } = render(<RegimePanel asset={ASSET} defaultOpen />);
    expect(container.textContent).toContain("weak signal");
  });

  it("shows nothing when no model has been trained", () => {
    query.value = { data: null, isPending: false, isError: false };
    const { container } = render(<RegimePanel asset={ASSET} defaultOpen />);
    expect(container).toBeEmptyDOMElement();
  });
});
