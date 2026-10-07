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
export type TrackRecord = components["schemas"]["TrackRecordOut"];
export type Summary = components["schemas"]["SummaryOut"];
export type Trust = components["schemas"]["TrustOut"];
export type Portfolio = components["schemas"]["PortfolioOut"];
export type Holding = components["schemas"]["Holding"];
export type PortfolioAnalysis = components["schemas"]["Analysis"];
export type AccountRecord = components["schemas"]["Record"];
export type Steps = components["schemas"]["Steps"];
export type BuyCheck = components["schemas"]["Check"];
export type Position = components["schemas"]["Position"];
export type Xray = components["schemas"]["Xray"];
export type LimitHorizon = components["schemas"]["LimitHorizon"];
export type PortfolioLimit = components["schemas"]["Limit"];
export type StressResult = components["schemas"]["StressResult"];
export type Relationships = components["schemas"]["Relationships"];
export type Pair = components["schemas"]["Pair"];
export type CorrelationGrid = components["schemas"]["Grid"];
export type Spillover = components["schemas"]["Spillover"];
export type WeekendGap = components["schemas"]["WeekendGap"];
export type Drivers = components["schemas"]["Drivers"];
export type DriverWindow = components["schemas"]["WindowResult"];
export type PortfolioPlan = components["schemas"]["Plan"];
export type WhatIf = components["schemas"]["WhatIf"];
export type RegularBuying = components["schemas"]["RegularBuying"];
export type Signals = components["schemas"]["SignalsOut"];
export type Signal = components["schemas"]["SignalOut"];
export type SignalRecords = components["schemas"]["SignalRecordsOut"];
export type SignalRecord = components["schemas"]["SignalRecordOut"];
export type Brief = components["schemas"]["BriefOut"];
export type Calendar = components["schemas"]["Calendar"];
export type SupportedAsset = components["schemas"]["SupportedAsset"];
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

async function sendJson<T>(method: "POST" | "PUT", path: string, body: unknown): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    // The server explains a refused request in plain words; pass that on when it does.
    const detail: unknown = await response
      .json()
      .then((payload: { detail?: unknown }) => payload.detail)
      .catch(() => undefined);
    throw new ApiError(
      response.status,
      typeof detail === "string" ? detail : `The server answered ${response.status} for ${path}`,
    );
  }
  return (await response.json()) as T;
}

export const postJson = <T>(path: string, body: unknown) => sendJson<T>("POST", path, body);
export const putJson = <T>(path: string, body: unknown) => sendJson<T>("PUT", path, body);

export function streamUrl(location: Pick<Location, "protocol" | "host">): string {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}${BASE}/stream`;
}
