// Live prices from the API's WebSocket. One connection for the whole app, kept open with
// reconnects. Live bars are for display only: stored history comes from the REST routes.

import { useEffect, useSyncExternalStore } from "react";

import { streamUrl, type LiveBar } from "./client";

export type StreamStatus = "connecting" | "open" | "closed";

export interface LivePrice {
  price: number;
  /** When the bar started, UTC. */
  ts: string;
  /** When this browser received it, in milliseconds. */
  receivedAt: number;
}

export interface LiveState {
  status: StreamStatus;
  prices: Readonly<Record<string, LivePrice>>;
}

export const INITIAL: LiveState = { status: "connecting", prices: {} };

/** A price is "live" if it arrived this recently. Otherwise the app shows the last close. */
export const LIVE_WINDOW_MS = 3 * 60_000;

function isLiveBar(event: unknown): event is LiveBar {
  if (typeof event !== "object" || event === null) return false;
  const e = event as Record<string, unknown>;
  return (
    e.type === "bar" &&
    typeof e.symbol === "string" &&
    typeof e.ts === "string" &&
    typeof e.close === "number"
  );
}

/** Pure reducer: fold one stream message into the state. Unknown messages are ignored. */
export function applyEvent(state: LiveState, event: unknown, now: number): LiveState {
  if (!isLiveBar(event)) return state;
  const previous = state.prices[event.symbol];
  // Ignore a bar older than the one already shown.
  if (previous && Date.parse(event.ts) < Date.parse(previous.ts)) return state;
  return {
    ...state,
    prices: {
      ...state.prices,
      [event.symbol]: { price: event.close, ts: event.ts, receivedAt: now },
    },
  };
}

export function isFresh(price: LivePrice | undefined, now: number): price is LivePrice {
  return price !== undefined && now - price.receivedAt <= LIVE_WINDOW_MS;
}

let state: LiveState = INITIAL;
const listeners = new Set<() => void>();

function setState(next: LiveState) {
  if (next === state) return;
  state = next;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const getSnapshot = () => state;

/** Open the stream and keep it open. Returns a function that closes it for good. */
export function connectStream(url: string): () => void {
  let socket: WebSocket | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let delay = 1000;
  let stopped = false;

  const open = () => {
    setState({ ...state, status: "connecting" });
    socket = new WebSocket(url);
    socket.onopen = () => {
      delay = 1000;
      setState({ ...state, status: "open" });
    };
    socket.onmessage = (message) => {
      try {
        setState(applyEvent(state, JSON.parse(String(message.data)), Date.now()));
      } catch {
        // A malformed message is skipped; the next one may be fine.
      }
    };
    socket.onclose = () => {
      setState({ ...state, status: "closed" });
      if (stopped) return;
      timer = setTimeout(open, delay);
      delay = Math.min(delay * 2, 30_000);
    };
  };
  open();

  return () => {
    stopped = true;
    if (timer) clearTimeout(timer);
    socket?.close();
  };
}

/** Mount once, near the top of the app. */
export function useLiveConnection() {
  useEffect(() => connectStream(streamUrl(window.location)), []);
}

export function useStreamStatus(): StreamStatus {
  return useSyncExternalStore(subscribe, getSnapshot).status;
}

export function useLivePrice(symbol: string | undefined): LivePrice | undefined {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot);
  return symbol ? snapshot.prices[symbol] : undefined;
}
