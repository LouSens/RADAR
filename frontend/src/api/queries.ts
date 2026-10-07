import { useEffect } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  getJson,
  postJson,
  putJson,
  type AccountRecord,
  type Asset,
  type Bars,
  type BuyCheck,
  type Calibration,
  type Health,
  type Holding,
  type LevelAnswer,
  type Portfolio,
  type PortfolioAnalysis,
  type Regime,
  type Risk,
  type Sentiment,
  type Simulation,
  type Steps,
  type Summary,
  type Timeframe,
  type Volatility,
  type Brief,
  type Calendar,
  type RegularBuying,
  type SignalRecords,
  type Signals,
  type SupportedAsset,
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
    // Holdings kept on an exchange are read again by the server when they are a few
    // minutes old; asking again is what lets a purchase show up by itself.
    refetchInterval: 5 * 60_000,
    refetchOnWindowFocus: true,
  });
}

/** When the holdings are read afresh, everything worked out from them is fetched again. */
export function useFollowHoldings() {
  const client = useQueryClient();
  const readAt = usePortfolio().data?.read_at;
  useEffect(() => {
    if (!readAt) return;
    void client.invalidateQueries({ queryKey: ["portfolio", "analysis"] });
    void client.invalidateQueries({ queryKey: ["portfolio", "steps"] });
  }, [client, readAt]);
}

/** Where the portfolio's risk comes from, its loss limits, and past episodes replayed. */
export function usePortfolioAnalysis() {
  return useQuery({
    queryKey: ["portfolio", "analysis"],
    queryFn: () => orNull(() => getJson<PortfolioAnalysis>("/portfolio/analysis")),
    refetchInterval: 10 * 60_000,
  });
}

/** What the holdings cost and made, from the exchange's own history. */
export function useAccountRecord() {
  return useQuery({
    queryKey: ["portfolio", "record"],
    queryFn: () => orNull(() => getJson<AccountRecord>("/portfolio/record")),
    staleTime: 60 * 60_000,
  });
}

/** The risk of one mix of the holdings, worked out for the account as it is. */
export function useMixRisk(weights: Record<string, number> | undefined) {
  return useQuery({
    queryKey: ["portfolio", "mix-risk", weights],
    queryFn: () => postJson<WhatIf>("/portfolio/what-if", { weights: weights ?? {} }),
    enabled: weights !== undefined,
    staleTime: 10 * 60_000,
  });
}

/** Whether a coin's price is high or low against its own recent past. */
export function useBuyCheck(coin: string) {
  return useQuery({
    queryKey: ["portfolio", "check", coin],
    queryFn: () => orNull(() => getJson<BuyCheck>(`/portfolio/check/${encodeURIComponent(coin)}`)),
    enabled: coin.length > 1,
    staleTime: 5 * 60_000,
  });
}

/** What to do with cash the plan does not keep: what to buy, at what prices, and why. */
export function useSteps() {
  return useQuery({
    queryKey: ["portfolio", "steps"],
    queryFn: () => orNull(() => getJson<Steps>("/portfolio/steps")),
    refetchInterval: 10 * 60_000,
  });
}

/** Say which coins that left the account without a sale were lost for good. */
export function useSetLostCoins() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (assets: string[]) => putJson<AccountRecord>("/portfolio/record/lost", { assets }),
    onSuccess: (record) => client.setQueryData(["portfolio", "record"], record),
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

/** Scheduled economic events: what is coming and how markets behaved around past ones. */
export function useCalendar() {
  return useQuery({
    queryKey: ["calendar"],
    queryFn: () => orNull(() => getJson<Calendar>("/events")),
    refetchInterval: 30 * 60_000,
  });
}

/** Today's brief, or null before one has been written. */
export function useBrief() {
  return useQuery({
    queryKey: ["brief"],
    queryFn: () => orNull(() => getJson<Brief>("/briefs/latest")),
    refetchInterval: 10 * 60_000,
  });
}

/** Recent signals, newest first, each with a summary of its track record. */
export function useSignals(filter: { symbol?: string; type?: string; limit?: number } = {}) {
  return useQuery({
    queryKey: ["signals", filter.symbol ?? "", filter.type ?? "", filter.limit ?? 50],
    queryFn: () =>
      getJson<Signals>("/signals", {
        symbol: filter.symbol,
        type: filter.type,
        limit: filter.limit ?? 50,
      }),
    refetchInterval: 10 * 60_000,
    // Changing the market or the kind keeps the list that is already on screen until the
    // next one arrives, so the card does not empty out and spring back on every tap.
    placeholderData: keepPreviousData,
  });
}

/** What followed one kind of signal in the past, on each market. */
export function useSignalRecords(type: string) {
  return useQuery({
    queryKey: ["signals", "records", type],
    queryFn: () => orNull(() => getJson<SignalRecords>(`/signals/track-records/${type}`)),
    placeholderData: keepPreviousData,
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

/** A plan of regular purchases run through simulated futures. Saves nothing. */
export function useRegularBuying() {
  return useMutation({
    mutationFn: (input: {
      weights: Record<string, number>;
      amount: number;
      every: number;
      purchases: number;
    }) => postJson<RegularBuying>("/portfolio/regular-buying", input),
  });
}

/** Find an asset by its ticker; a new one has its price history fetched first. */
export function useLookup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { ticker: string; kind: "stock" | "crypto" }) =>
      postJson<SupportedAsset>("/portfolio/lookup", input),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["portfolio"], exact: true });
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
