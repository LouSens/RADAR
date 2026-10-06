import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe as suite, expect, it, vi } from "vitest";

import type { Asset, TrackRecord } from "../api/client";
import { describe, TrackRecordPanel } from "./TrackRecordPanel";

const state = vi.hoisted(() => ({ record: null as unknown }));
vi.mock("../api/queries", () => ({ useTrackRecord: () => ({ data: state.record }) }));

const BITCOIN: Asset = {
  symbol: "BTC/USD",
  slug: "btc-usd",
  name: "Bitcoin",
  asset_class: "crypto",
  is_primary: true,
  history_start: "2021-01-01",
  news_start: "2022-01-01",
  trades_continuously: true,
};

function row(values: Partial<TrackRecord["rows"][number]>): TrackRecord["rows"][number] {
  return {
    kind: "outlook_range",
    horizon_days: 7,
    key: "0.8",
    recorded: 40,
    resolved: 0,
    held: null,
    held_share: null,
    held_low: null,
    held_high: null,
    expected_share: 0.8,
    forecast_to_outcome: null,
    first_as_of: "2026-10-05T00:00:00Z",
    last_as_of: "2026-11-13T00:00:00Z",
    ...values,
  };
}

const RECORD: TrackRecord = {
  symbol: "BTC/USD",
  recording_since: "2026-10-05T00:00:00Z",
  recorded: 120,
  resolved: 63,
  rows: [
    row({ resolved: 33, held: 27, held_share: 0.818, held_low: 0.66, held_high: 0.91 }),
    row({ horizon_days: 30, recorded: 40 }),
    row({
      kind: "volatility",
      key: "har",
      horizon_days: 1,
      resolved: 30,
      forecast_to_outcome: 1.08,
      expected_share: null,
    }),
  ],
};

suite("TrackRecordPanel", () => {
  afterEach(cleanup);
  beforeEach(() => {
    state.record = RECORD;
  });

  it("shows nothing before any forecast has been logged", () => {
    state.record = { ...RECORD, rows: [], recording_since: null };
    expect(render(<TrackRecordPanel asset={BITCOIN} />).container).toBeEmptyDOMElement();
  });

  it("shows what held against what should have, with the range", () => {
    render(<TrackRecordPanel asset={BITCOIN} />);
    expect(screen.getByText("80% outlook range, 1 week")).toBeInTheDocument();
    expect(screen.getByText("Held 27 of 33: 82% (66% to 91%); should be about 80%")).toBeInTheDocument();
    expect(screen.getByText(/forecasts ran 8% above what happened/)).toBeInTheDocument();
  });

  it("says so when nothing has come due yet", () => {
    render(<TrackRecordPanel asset={BITCOIN} />);
    expect(screen.getByText("No results yet")).toBeInTheDocument();
    expect(screen.getByText(/never edited/)).toBeInTheDocument();
  });

  it("names each kind of forecast plainly", () => {
    expect(describe(row({ kind: "loss_limit", key: "0.99", horizon_days: 1 }))).toBe(
      "99% loss limit, 1 day",
    );
    expect(describe(row({ kind: "volatility", key: "har", horizon_days: 7 }))).toBe(
      "Expected swings, 1 week",
    );
  });
});
