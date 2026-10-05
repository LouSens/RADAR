import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Health } from "../api/client";
import { SystemPage } from "./SystemPage";

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

describe("SystemPage", () => {
  it("shows coverage with sample sizes, staleness, and gaps", () => {
    health.value = { data: DATA, isPending: false, isError: false };
    render(<SystemPage />);
    expect(screen.getByText(/Some data is behind/)).toBeInTheDocument();
    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("82 passed")).toBeInTheDocument();
    expect(screen.getByText("50,453")).toBeInTheDocument();
    expect(screen.getByText("0.05%")).toBeInTheDocument();
    expect(screen.getByText("12 hours ago")).toBeInTheDocument();
    expect(screen.getByText("behind")).toBeInTheDocument();
  });

  it("counts data checks that need review", () => {
    health.value = {
      data: { ...DATA, quality: { ...DATA.quality, warnings: 2, failures: 1 } },
      isPending: false,
      isError: false,
    };
    render(<SystemPage />);
    expect(screen.getByText("3 to review")).toBeInTheDocument();
  });

  it("says so when status cannot be loaded", () => {
    health.value = { data: undefined, isPending: false, isError: true };
    render(<SystemPage />);
    expect(screen.getByText(/unavailable right now/)).toBeInTheDocument();
  });

  it("never uses advice words", () => {
    health.value = { data: DATA, isPending: false, isError: false };
    const { container } = render(<SystemPage />);
    expect(container.textContent).not.toMatch(/\b(buy|sell|you should)\b/i);
  });
});
