import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  getJson,
  postJson,
  putJson,
  type Asset,
  type Bars,
  type Calibration,
  type Drivers,
  type EventStudy,
  type Health,
  type Holding,
  type LevelAnswer,
  type NewsTest,
  type Portfolio,
  type PortfolioAnalysis,
  type Regime,
  type Relationships,
  type Risk,
  type Sentiment,
  type Simulation,
  type Summary,
  type Timeframe,
  type TrackRecord,
  type Volatility,
  type WhatIf,
} from "./client";

export function useAssets() {
  return useQuery({
    queryKey: ["assets"],
    queryFn: () => getJson<Asset[]>("/assets"),
    staleTime: 5 * 60_000,
  });
}

export function useBars(slug: string | undefined, timeframe: Timeframe, limit: number) {
  return useQuery({
    queryKey: ["bars", slug, timeframe, limit],
    queryFn: () => getJson<Bars>(`/assets/${slug}/bars`, { timeframe, limit }),
    enabled: slug !== undefined,
    // Stored bars change once an hour; a minute is frequent enough to pick that up.
    refetchInterval: 60_000,
  });
}

/** Bars from `days` ago until now. The start is worked out when the request is made. */
export function useBarsSince(slug: string | undefined, timeframe: Timeframe, days: number) {
  return useQuery({
    queryKey: ["bars-since", slug, timeframe, days],
    queryFn: () => {
      const start = new Date(Date.now() - days * 86_400_000).toISOString();
      return getJson<Bars>(`/assets/${slug}/bars`, { timeframe, start, limit: 5000 });
    },
    enabled: slug !== undefined,
    refetchInterval: 60_000,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => getJson<Health>("/health"),
    refetchInterval: 15_000,
  });
}

/** The market regime for an asset. `null` means no model has been trained for it yet. */
export function useRegime(slug: string | undefined, days = 365) {
  return useQuery({
    queryKey: ["regime", slug, days],
    queryFn: async () => {
      try {
        return await getJson<Regime>(`/assets/${slug}/regime`, { days });
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    enabled: slug !== undefined,
    refetchInterval: 5 * 60_000,
  });
}

/** Runs a request and gives `null` where the server has nothing stored yet. */
async function orNull<T>(request: () => Promise<T>): Promise<T | null> {
  try {
    return await request();
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** The latest stored simulator run for an asset. */
export function useSimulation(slug: string | undefined) {
  return useQuery({
    queryKey: ["simulation", slug],
    queryFn: () => orNull(() => getJson<Simulation>(`/assets/${slug}/simulation`)),
    enabled: slug !== undefined,
    refetchInterval: 5 * 60_000,
  });
}

/** How often the simulator's past ranges held. */
export function useCalibration(slug: string | undefined) {
  return useQuery({
    queryKey: ["calibration", slug],
    queryFn: () => orNull(() => getJson<Calibration>(`/assets/${slug}/calibration`)),
    enabled: slug !== undefined,
    staleTime: 60 * 60_000,
  });
}

/** Chances for a price level the reader enters, counted from the stored run. */
export function useLevel(slug: string) {
  return useMutation({
    mutationFn: (input: { level: number; horizon_days: number }) =>
      postJson<LevelAnswer>(`/assets/${slug}/simulation/level`, input),
  });
}

/** The volatility forecast, its history, and how each method scored. */
export function useVolatility(slug: string | undefined) {
  return useQuery({
    queryKey: ["volatility", slug],
    queryFn: () => orNull(() => getJson<Volatility>(`/assets/${slug}/volatility`)),
    enabled: slug !== undefined,
    refetchInterval: 5 * 60_000,
  });
}

/** Loss limits and how often each has been broken. */
export function useRisk(slug: string | undefined) {
  return useQuery({
    queryKey: ["risk", slug],
    queryFn: () => orNull(() => getJson<Risk>(`/assets/${slug}/risk`)),
    enabled: slug !== undefined,
    refetchInterval: 5 * 60_000,
  });
}

/** News tone over the last `days`, the strongest articles, and the model's accuracy. */
export function useSentiment(slug: string | undefined, days = 90) {
  return useQuery({
    queryKey: ["sentiment", slug, days],
    queryFn: () => orNull(() => getJson<Sentiment>(`/assets/${slug}/sentiment`, { days })),
    enabled: slug !== undefined,
    refetchInterval: 5 * 60_000,
  });
}

/** Whether news tone has led price, followed it, or neither. */
export function useEventStudy(slug: string | undefined) {
  return useQuery({
    queryKey: ["event-study", slug],
    queryFn: () => orNull(() => getJson<EventStudy>(`/assets/${slug}/event-study`)),
    enabled: slug !== undefined,
    staleTime: 60 * 60_000,
  });
}

/** Forecasts logged on the day they were made, and how they have turned out. */
export function useTrackRecord(slug: string | undefined) {
  return useQuery({
    queryKey: ["track-record", slug],
    queryFn: () => orNull(() => getJson<TrackRecord>(`/assets/${slug}/track-record`)),
    enabled: slug !== undefined,
    refetchInterval: 10 * 60_000,
  });
}

/** The answers in brief for a market, what changed this week, and a trust grade per claim. */
export function useSummary(slug: string | undefined) {
  return useQuery({
    queryKey: ["summary", slug],
    queryFn: () => orNull(() => getJson<Summary>(`/assets/${slug}/summary`)),
    enabled: slug !== undefined,
    refetchInterval: 5 * 60_000,
  });
}

/** The saved holdings and the assets that can be held. */
export function usePortfolio() {
  return useQuery({
    queryKey: ["portfolio"],
    queryFn: () => getJson<Portfolio>("/portfolio"),
  });
}

/** Where the portfolio's risk comes from, its loss limits, and past episodes replayed. */
export function usePortfolioAnalysis() {
  return useQuery({
    queryKey: ["portfolio", "analysis"],
    queryFn: () => orNull(() => getJson<PortfolioAnalysis>("/portfolio/analysis")),
    refetchInterval: 10 * 60_000,
  });
}

/** Save typed-in holdings, the text of a CSV file, or what Binance holds. Each replaces
 *  what was saved. */
export function useSavePortfolio() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { holdings: Holding[] } | { csv: string } | { binance: true }) =>
      "binance" in input
        ? postJson<Portfolio>("/portfolio/binance", {})
        : "csv" in input
          ? postJson<Portfolio>("/portfolio/import", input)
          : putJson<Portfolio>("/portfolio", input),
    onSuccess: (saved) => {
      client.setQueryData(["portfolio"], saved);
      void client.invalidateQueries({ queryKey: ["portfolio", "analysis"] });
    },
  });
}

/** How the markets move together: correlations, risk transmission, weekend gaps. */
export function useRelationships() {
  return useQuery({
    queryKey: ["relationships"],
    queryFn: () => orNull(() => getJson<Relationships>("/relationships")),
    refetchInterval: 10 * 60_000,
  });
}

/** Which outside forces a market has been moving with. */
export function useDrivers(slug: string | undefined) {
  return useQuery({
    queryKey: ["drivers", slug],
    queryFn: () => orNull(() => getJson<Drivers>(`/assets/${slug}/drivers`)),
    enabled: slug !== undefined,
    refetchInterval: 10 * 60_000,
  });
}

/** Whether adding news improved the forecast of a market's daily movement. */
export function useNewsTest(slug: string | undefined) {
  return useQuery({
    queryKey: ["news-and-swings", slug],
    queryFn: () => orNull(() => getJson<NewsTest>(`/assets/${slug}/news-and-swings`)),
    enabled: slug !== undefined,
    staleTime: 60 * 60_000,
  });
}

/** Choose, change, or clear the risk level and split the portfolio is compared with. */
export function useSetTarget() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (
      input:
        | { level: "low" | "moderate" | "high" | null; split?: string }
        | { weights: Record<string, number> },
    ) => putJson<PortfolioAnalysis>("/portfolio/target", input),
    onSuccess: (analysis) => {
      client.setQueryData(["portfolio", "analysis"], analysis);
    },
  });
}

/** The risk figures for a mix being tried. Saves nothing. */
export function useWhatIf() {
  return useMutation({
    mutationFn: (input: { weights: Record<string, number> }) =>
      postJson<WhatIf>("/portfolio/what-if", input),
  });
}

