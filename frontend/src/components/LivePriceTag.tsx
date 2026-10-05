import { useEffect, useState } from "react";

import type { Asset, Bar } from "../api/client";
import { isFresh, useLivePrice, type LivePrice } from "../api/live";
import { formatPrice } from "../lib/format";
import { formatDateTime, zoneLabel } from "../lib/time";

/** Re-render on a timer so a live price stops being called live once it goes quiet. */
function useNow(everyMs = 15_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), everyMs);
    return () => clearInterval(timer);
  }, [everyMs]);
  return now;
}

/** The live price for an asset if one arrived recently, else undefined. */
export function useFreshPrice(symbol: string | undefined): LivePrice | undefined {
  const live = useLivePrice(symbol);
  const now = useNow();
  return isFresh(live, now) ? live : undefined;
}

export function LiveBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-calm">
      <span className="live-dot inline-block h-1.5 w-1.5 rounded-full bg-calm" aria-hidden="true" />
      Live
    </span>
  );
}

/**
 * The current price with an honest label: "Live" only when a price arrived in the last
 * few minutes, otherwise the last stored price and when it was.
 */
export function LivePriceTag({
  asset,
  lastBar,
  size = "md",
  align = "right",
}: {
  asset: Asset;
  lastBar: Bar | undefined;
  size?: "md" | "lg";
  align?: "left" | "right";
}) {
  const live = useFreshPrice(asset.symbol);
  const price = size === "lg" ? "text-fluid-price" : "text-2xl";
  const side = align === "right" ? "text-right items-end" : "text-left items-start";
  if (live) {
    return (
      <div className={`flex flex-col ${side}`}>
        <div className={`num ${price} font-semibold leading-none`}>{formatPrice(live.price)}</div>
        <div className="mt-1.5">
          <LiveBadge />
        </div>
      </div>
    );
  }
  if (!lastBar) {
    return <div className={`text-sm text-muted ${side}`}>No price yet</div>;
  }
  return (
    <div className={`flex flex-col ${side}`}>
      <div className={`num ${price} font-semibold leading-none`}>{formatPrice(lastBar.close)}</div>
      <div className="mt-1.5 max-w-[26ch] text-xs leading-snug text-muted">
        Not live · last stored price, {formatDateTime(lastBar.ts)} {zoneLabel()}
        {asset.trades_continuously ? "" : " · trades in US market hours"}
      </div>
    </div>
  );
}
