import type { CSSProperties } from "react";
import { useParams } from "react-router-dom";

import { useMarket } from "../api/market";
import { useAssets } from "../api/queries";
import { MarketStage } from "../components/MarketStage";
import { Change, Message, RangeBar, StatRow, assetColorVar } from "../components/ui";
import { formatPrice } from "../lib/format";
import { formatDate } from "../lib/time";

export function AssetPage() {
  const { slug } = useParams();
  const assets = useAssets();
  const asset = assets.data?.find((a) => a.slug === slug);
  const market = useMarket(asset);

  if (assets.isPending) return <Message>Loading…</Message>;
  if (!asset) return <Message>That market could not be found.</Message>;

  const price = (value: number | undefined) => (value === undefined ? "–" : formatPrice(value));

  return (
    <div
      className="flex flex-col gap-5 sm:gap-7"
      style={{ "--tint": `var(${assetColorVar(asset)})` } as CSSProperties}
    >
      <div className="aurora" aria-hidden="true" />

      <div className="rise">
        <MarketStage key={asset.slug} asset={asset} allowCandles />
      </div>

      <section className="glass rise rise-2 grid grid-cols-1 gap-x-12 gap-y-6 p-5 sm:p-7 lg:grid-cols-2">
        <div>
          <h2 className="mb-2 text-base font-semibold tracking-tight">Performance</h2>
          <dl>
            <StatRow label="Previous close">{price(market.previousClose)}</StatRow>
            <StatRow label="Since previous close">
              <Change value={market.sinceClose} />
            </StatRow>
            <StatRow label="Past week">
              <Change value={market.week} />
            </StatRow>
            <StatRow label="Past month">
              <Change value={market.month} />
            </StatRow>
            <StatRow label="Past year">
              <Change value={market.year} />
            </StatRow>
          </dl>
        </div>
        <div>
          <h2 className="mb-4 text-base font-semibold tracking-tight">52-week range</h2>
          {market.yearRange && market.price !== undefined ? (
            <RangeBar
              range={market.yearRange}
              price={market.price}
              colorVar={assetColorVar(asset)}
              format={formatPrice}
            />
          ) : (
            <p className="text-sm text-muted">Not enough history yet.</p>
          )}
          <dl className="mt-4">
            <StatRow label="Trading hours">
              {asset.trades_continuously ? "Around the clock" : "US market hours"}
            </StatRow>
            <StatRow label="History since">{formatDate(asset.history_start)}</StatRow>
          </dl>
        </div>
      </section>
    </div>
  );
}
