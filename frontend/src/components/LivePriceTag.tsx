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

/**
 * The current price with an honest label: "Live" only when a price arrived in the last
 * few minutes, otherwise the last stored close and when it was.
 */
export function LivePriceTag({ asset, lastBar }: { asset: Asset; lastBar: Bar | undefined }) {
  const live = useFreshPrice(asset.symbol);
  if (live) {
    return (
      <div className="text-right">
        <div className="num text-2xl font-medium">{formatPrice(live.price)}</div>
        <div className="flex items-center justify-end gap-1.5 text-xs text-calm">
          <span className="live-dot inline-block h-1.5 w-1.5 rounded-full bg-calm" aria-hidden="true" />
          Live
        </div>
      </div>
    );
  }
  if (!lastBar) {
    return <div className="text-right text-sm text-muted">No price yet</div>;
  }
  return (
    <div className="text-right">
      <div className="num text-2xl font-medium">{formatPrice(lastBar.close)}</div>
      <div className="text-xs text-muted">
        Not live · last stored price, {formatDateTime(lastBar.ts)} {zoneLabel()}
        {asset.trades_continuously ? "" : " · trades in US market hours"}
      </div>
    </div>
  );
}
