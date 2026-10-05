import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Health } from "../api/client";
import { StatusPage } from "./StatusPage";

const health = vi.hoisted(() => ({ value: {} as unknown }));

vi.mock("../api/queries", () => ({ useHealth: () => health.value }));
vi.mock("../api/live", () => ({ useStreamStatus: () => "open" }));

const DATA: Health = {
  status: "degraded",
  generated_at: "2026-10-05T09:00:00Z",
  database: true,
  last_sync: "2026-10-05T08:01:00Z",
  stream_clients: 1,
  quality: { last_run: "2026-10-05T08:10:00Z", findings: 82, warnings: 0, failures: 0 },
  series: [
    {
      symbol: "BTC/USD",
      timeframe: "1Hour",
      is_primary: true,
      bars: 50453,
      first_ts: "2021-01-01T00:00:00Z",
      last_ts: "2026-10-05T08:00:00Z",
      lag_seconds: 300,
      stale: false,
      missing_share: 0.000535,
    },
    {
      symbol: "PAXG/USD",
      timeframe: "1Hour",
      is_primary: false,
      bars: 48479,
      first_ts: "2021-01-01T00:00:00Z",
      last_ts: "2026-10-04T20:00:00Z",
      lag_seconds: 12 * 3600,
      stale: true,
      missing_share: null,
    },
  ],
};

describe("StatusPage", () => {
  it("shows coverage with sample sizes, staleness, and missing shares", () => {
    health.value = { data: DATA, isPending: false, isError: false };
    render(<StatusPage />);
    expect(screen.getByText("Some data needs attention")).toBeInTheDocument();
    expect(screen.getByText("50,453")).toBeInTheDocument();
    expect(screen.getByText("0.05%")).toBeInTheDocument();
    expect(screen.getByText("not checked")).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(screen.getByText("Behind")).toBeInTheDocument();
    expect(screen.getByText("12 hours ago")).toBeInTheDocument();
  });

  it("says so when the API does not answer", () => {
    health.value = { data: undefined, isPending: false, isError: true };
    render(<StatusPage />);
    expect(screen.getByText(/The API did not answer/)).toBeInTheDocument();
  });

  it("never uses advice words", () => {
    health.value = { data: DATA, isPending: false, isError: false };
    const { container } = render(<StatusPage />);
    expect(container.textContent).not.toMatch(/\b(buy|sell|you should)\b/i);
  });
});
