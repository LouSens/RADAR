import type { CSSProperties } from "react";
import { Link } from "react-router-dom";

import type { Asset } from "../api/client";
import { useMarket } from "../api/market";
import { useSummary } from "../api/queries";
import { formatPrice } from "../lib/format";
import { Change, Sparkline, assetColorVar, shortName } from "./ui";
import { stateColour } from "./viz";

/**
 * One market at a glance: its name, price, today's change, and the week as a line. Small
 * enough that the three sit side by side on a phone. Tap to open the market.
 */
export function MarketCard({ asset }: { asset: Asset }) {
  const market = useMarket(asset);
  const state = useSummary(asset.slug).data?.state;
  return (
    <Link
      to={`/asset/${asset.slug}`}
      className="tile toned press flex min-w-0 flex-col"
      style={{ "--tone": `var(${assetColorVar(asset)})` } as CSSProperties}
      aria-label={shortName(asset)}
    >
      <span className="flex min-w-0 items-center gap-1.5">
        <span
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ background: `var(${assetColorVar(asset)})` }}
          aria-hidden="true"
        />
        <span className="truncate text-[13px] font-medium @2xl:text-sm">{shortName(asset)}</span>
      </span>
      <span className="num mt-2 block truncate text-[1.02rem] font-semibold leading-tight tracking-tight @2xl:text-[1.4rem]">
        {market.price === undefined ? "–" : formatPrice(market.price)}
      </span>
      <Change value={market.sinceClose} className="mt-0.5 block text-xs @2xl:text-sm" />
      <span className="mt-2 block h-8 w-full @2xl:h-11">
        <Sparkline values={market.weekCloses} colorVar={assetColorVar(asset)} />
      </span>
      {state && (
        <span
          className="mt-2 block truncate text-[11px] font-medium capitalize @2xl:text-xs"
          style={{ color: stateColour(state.label) }}
        >
          {state.label}
        </span>
      )}
    </Link>
  );
}
