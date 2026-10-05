// The only place the app calls the network. Components use the hooks in queries.ts.

import type { components } from "./schema";

export type Asset = components["schemas"]["AssetOut"];
export type Bar = components["schemas"]["BarOut"];
export type Bars = components["schemas"]["BarsOut"];
export type Health = components["schemas"]["HealthOut"];
export type SeriesStatus = components["schemas"]["SeriesStatus"];
export type LiveBar = components["schemas"]["LiveBar"];
export type LiveNews = components["schemas"]["LiveNews"];
export type Timeframe = "1Hour" | "1Day";

const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Params = Record<string, string | number | undefined>;

export async function getJson<T>(path: string, params: Params = {}): Promise<T> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value));
  }
  const suffix = query.size ? `?${query}` : "";
  const response = await fetch(`${BASE}${path}${suffix}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new ApiError(response.status, `The server answered ${response.status} for ${path}`);
  }
  return (await response.json()) as T;
}

export function streamUrl(location: Pick<Location, "protocol" | "host">): string {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}${BASE}/stream`;
}
