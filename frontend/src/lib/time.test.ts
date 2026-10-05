import { describe, expect, it } from "vitest";

import { formatChange, formatPrice, formatShare } from "./format";
import { formatDateTime, formatDuration, isoDateIn, tradingDay, zoneLabel } from "./time";

describe("time", () => {
  it("shows an instant in the viewer's zone and names the zone", () => {
    // Midnight UTC is 08:00 in GMT+8.
    expect(formatDateTime("2026-10-05T00:00:00Z", "Asia/Singapore")).toBe("5 Oct 2026, 08:00");
    expect(zoneLabel("Asia/Singapore")).toBe("GMT+8");
    expect(formatDateTime("2026-10-05T00:00:00Z", "UTC")).toBe("5 Oct 2026, 00:00");
  });

  it("assigns daily bars to the right trading day", () => {
    // A stock daily bar is stamped at midnight New York: 04:00 UTC in summer, 05:00 in winter.
    expect(tradingDay("2026-07-01T04:00:00Z", "stock")).toBe("2026-07-01");
    expect(tradingDay("2026-01-16T05:00:00Z", "stock")).toBe("2026-01-16");
    expect(tradingDay("2026-10-04T00:00:00Z", "crypto")).toBe("2026-10-04");
    // The same instant is still the previous day in New York.
    expect(isoDateIn("2026-10-04T00:00:00Z", "America/New_York")).toBe("2026-10-03");
  });

  it("describes durations roughly", () => {
    expect(formatDuration(45)).toBe("45 seconds");
    expect(formatDuration(60 * 60)).toBe("60 minutes");
    expect(formatDuration(2 * 3600)).toBe("2 hours");
    expect(formatDuration(3 * 86400)).toBe("3 days");
    expect(formatDuration(-10)).toBe("0 seconds");
  });
});

describe("format", () => {
  it("formats prices by size", () => {
    expect(formatPrice(86890.4)).toBe("$86,890");
    expect(formatPrice(385.2)).toBe("$385.20");
    expect(formatPrice(0.5123)).toBe("$0.5123");
  });

  it("formats changes and shares", () => {
    expect(formatChange(0.0124)).toBe("+1.24%");
    expect(formatChange(-0.05)).toBe("−5.00%");
    expect(formatChange(0)).toBe("0.00%");
    expect(formatShare(0.0396)).toBe("3.96%");
  });
});
