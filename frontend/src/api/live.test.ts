import { describe, expect, it } from "vitest";

import { streamUrl } from "./client";
import { INITIAL, LIVE_WINDOW_MS, applyEvent, isFresh } from "./live";

const bar = (symbol: string, ts: string, close: number) => ({
  type: "bar",
  symbol,
  ts,
  open: close,
  high: close,
  low: close,
  close,
});

describe("live stream state", () => {
  it("keeps the latest price per asset", () => {
    let state = applyEvent(INITIAL, bar("BTC/USD", "2026-10-05T09:00:00Z", 100), 1000);
    state = applyEvent(state, bar("GLD", "2026-10-05T09:00:00Z", 50), 2000);
    state = applyEvent(state, bar("BTC/USD", "2026-10-05T09:01:00Z", 101), 3000);
    expect(state.prices["BTC/USD"]).toEqual({
      price: 101,
      ts: "2026-10-05T09:01:00Z",
      receivedAt: 3000,
    });
    expect(state.prices["GLD"]?.price).toBe(50);
  });

  it("ignores a bar older than the one shown", () => {
    const first = applyEvent(INITIAL, bar("BTC/USD", "2026-10-05T09:05:00Z", 105), 1000);
    const second = applyEvent(first, bar("BTC/USD", "2026-10-05T09:00:00Z", 1), 2000);
    expect(second).toBe(first);
  });

  it("ignores messages that are not bars", () => {
    for (const event of [{ type: "hello" }, { type: "news", id: 1 }, null, "text", { type: "bar" }]) {
      expect(applyEvent(INITIAL, event, 1000)).toBe(INITIAL);
    }
  });

  it("stops calling a price live once it goes quiet", () => {
    const state = applyEvent(INITIAL, bar("GLD", "2026-10-05T09:00:00Z", 50), 1000);
    const price = state.prices["GLD"];
    expect(isFresh(price, 1000 + LIVE_WINDOW_MS)).toBe(true);
    expect(isFresh(price, 1001 + LIVE_WINDOW_MS)).toBe(false);
    expect(isFresh(undefined, 1000)).toBe(false);
  });
});

describe("stream address", () => {
  it("uses the page's own host and a secure socket on https", () => {
    expect(streamUrl({ protocol: "http:", host: "localhost:5173" })).toBe(
      "ws://localhost:5173/api/v1/stream",
    );
    expect(streamUrl({ protocol: "https:", host: "radar.example" })).toBe(
      "wss://radar.example/api/v1/stream",
    );
  });
});
