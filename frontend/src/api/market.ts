// Everything the screens show about one asset's price, gathered in one place.

import { useEffect, useState } from "react";

import { change, closeDaysAgo, previousClose, rangeOver } from "../lib/stats";
import type { Asset } from "./client";
import { isFresh, useLivePrice } from "./live";
import { useBars, useBarsSince } from "./queries";

const HOUR_MS = 3_600_000;

/** The current time, refreshed on a timer so "live" and "as of" stay truthful. */
export function useNow(everyMs = 15_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), everyMs);
    return () => clearInterval(timer);
  }, [everyMs]);
  return now;
}

export function useMarket(asset: Asset | undefined) {
  const now = useNow();
  const week = useBarsSince(asset?.slug, "1Hour", 7);
  const daily = useBars(asset?.slug, "1Day", 370);
  const stream = useLivePrice(asset?.symbol);
  const live = isFresh(stream, now) ? stream : undefined;

  const hours = week.data?.bars ?? [];
  const days = daily.data?.bars ?? [];
  const lastHour = hours.at(-1);
  const price = live?.price ?? lastHour?.close;

  return {
    isPending: week.isPending || daily.isPending,
    isError: week.isError || daily.isError,
    /** A live price, when one arrived in the last few minutes. */
    live,
    price,
    /** When the shown price was true, if it is not live: the end of the last stored hour. */
    asOf: live || !lastHour ? undefined : Date.parse(lastHour.ts) + HOUR_MS,
    weekCloses: hours.map((bar) => bar.close),
    sinceClose: change(previousClose(days), price),
    week: change(closeDaysAgo(days, 7, now), price),
    month: change(closeDaysAgo(days, 30, now), price),
    year: change(closeDaysAgo(days, 365, now), price),
    previousClose: previousClose(days),
    yearRange: rangeOver(days, 365, now, price),
  };
}
