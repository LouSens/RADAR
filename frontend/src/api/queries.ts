import { useQuery } from "@tanstack/react-query";

import { getJson, type Asset, type Bars, type Health, type Timeframe } from "./client";

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
