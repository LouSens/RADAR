// The only place the app calls the network. Components use the hooks in queries.ts.

import type { components } from "./schema";

export type Asset = components["schemas"]["AssetOut"];
export type Bar = components["schemas"]["BarOut"];
export type Bars = components["schemas"]["BarsOut"];
export type Health = components["schemas"]["HealthOut"];
export type SeriesStatus = components["schemas"]["SeriesStatus"];
export type LiveBar = components["schemas"]["LiveBar"];
export type LiveNews = components["schemas"]["LiveNews"];
export type Regime = components["schemas"]["RegimeOut"];
export type Simulation = components["schemas"]["SimulationOut"];
export type OutlookHorizon = components["schemas"]["OutlookHorizon"];
export type OutlookRange = components["schemas"]["OutlookRange"];
export type Calibration = components["schemas"]["CalibrationOut"];
export type CalibrationRow = components["schemas"]["CalibrationRowOut"];
export type LevelAnswer = components["schemas"]["LevelOut"];
export type Volatility = components["schemas"]["VolatilityOut"];
export type VolatilityHorizon = components["schemas"]["VolatilityHorizonOut"];
export type Risk = components["schemas"]["RiskOut"];
export type RiskHorizon = components["schemas"]["RiskHorizonOut"];
export type RiskMethod = components["schemas"]["RiskMethodOut"];
export type Sentiment = components["schemas"]["SentimentOut"];
export type EventStudy = components["schemas"]["EventStudyOut"];
export type TrackRecord = components["schemas"]["TrackRecordOut"];
export type Summary = components["schemas"]["SummaryOut"];
export type Trust = components["schemas"]["TrustOut"];
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

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
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
