import { useMutation, useQuery } from "@tanstack/react-query";

import {
  ApiError,
  getJson,
  postJson,
  type Asset,
  type Bars,
  type Calibration,
  type Health,
  type LevelAnswer,
  type Regime,
  type Risk,
  type Simulation,
  type Timeframe,
  type Volatility,
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
