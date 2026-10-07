import { Link } from "react-router-dom";

import type { Asset } from "../api/client";
import { useMarket } from "../api/market";
import { useAssets } from "../api/queries";
import { MarketCard } from "../components/MarketCard";
import { Caption, Change, Message, RangeBar, assetColorVar, shortName } from "../components/ui";
import { formatPrice } from "../lib/format";

const PERIODS = ["Day", "Week", "Month", "Year"] as const;
const GRID =
  "grid grid-cols-4 gap-x-4 @4xl:grid-cols-[minmax(0,1.1fr)_repeat(4,5.5rem)_minmax(0,1.6fr)] @4xl:gap-x-6";

function CompareRow({ asset }: { asset: Asset }) {
  const market = useMarket(asset);
  const values = [market.sinceClose, market.week, market.month, market.year];
  return (
    <div className={`${GRID} items-center gap-y-3 border-b border-line py-4 last:border-b-0`}>
      <Link
        to={`/asset/${asset.slug}`}
        className="group col-span-4 flex min-w-0 items-center gap-2.5 @4xl:col-span-1"
      >
        <span
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ background: `var(${assetColorVar(asset)})` }}
          aria-hidden="true"
        />
        <span className="truncate font-medium group-hover:text-accent">{shortName(asset)}</span>
      </Link>
      {values.map((value, i) => (
        <span key={PERIODS[i]} className="text-sm @4xl:text-right">
          <span className="label mb-0.5 block text-xs @4xl:hidden">{PERIODS[i]}</span>
          <Change value={value} />
        </span>
      ))}
      <div className="col-span-4 @4xl:col-span-1">
        {market.yearRange && market.price !== undefined && (
          <RangeBar
            range={market.yearRange}
            price={market.price}
            colorVar={assetColorVar(asset)}
            format={formatPrice}
          />
        )}
      </div>
    </div>
  );
}

/** The three markets and how they compare. */
export function MarketsPage() {
  const assets = useAssets();
  const primary = assets.data?.filter((a) => a.is_primary) ?? [];
  return (
    <div className="flex flex-col gap-4 @xl:gap-6">
      <header>
        <h1 className="title">Markets</h1>
      </header>
      {assets.isError && <Message>Markets are unavailable right now.</Message>}
      <div className="grid grid-cols-3 gap-2 @xl:gap-4">
        {primary.map((asset) => (
          <MarketCard key={asset.slug} asset={asset} />
        ))}
      </div>

      {primary.length > 0 && (
        <section className="glass px-4 pb-3 pt-4 @xl:px-7 @xl:pt-6">
          <div className={`${GRID} items-end border-b border-line pb-3`}>
            <h2 className="col-span-4 text-base font-semibold tracking-tight @4xl:col-span-1">
              Side by side
            </h2>
            {PERIODS.map((heading) => (
              <span key={heading} className="label hidden text-right text-xs @4xl:block">
                {heading}
              </span>
            ))}
            <span className="label hidden text-xs @4xl:block">52-week range</span>
          </div>
          {primary.map((asset) => (
            <CompareRow key={asset.slug} asset={asset} />
          ))}
          <Caption
            facts={[
              { label: "Day", value: "Change since the previous close" },
              { label: "Week, month, year", value: "Against the close 7, 30 and 365 days ago" },
              {
                label: "Range",
                value: "Lowest to highest price of the last 365 days, today marked",
              },
            ]}
          />
        </section>
      )}
    </div>
  );
}
