import { useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";

import type { Asset } from "../api/client";
import { useMarket, useNow } from "../api/market";
import { useAssets } from "../api/queries";
import { BriefCard } from "../components/BriefCard";
import { LatestSignals } from "../components/LatestSignals";
import { MarketStage } from "../components/MarketStage";
import { Change, Message, RangeBar, Sparkline, assetColorVar, shortName } from "../components/ui";
import { formatPrice } from "../lib/format";
import { zoneLabel } from "../lib/time";

/** One market in the picker. Choosing it puts that market on the stage below. */
function MarketOption({
  asset,
  selected,
  onSelect,
}: {
  asset: Asset;
  selected: boolean;
  onSelect: () => void;
}) {
  const market = useMarket(asset);
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className="market min-w-0 p-3.5 @xl:p-5"
      style={{ "--tone": `var(${assetColorVar(asset)})` } as CSSProperties}
    >
      <span className="flex items-center gap-2 text-sm">
        <span
          className="hidden h-2 w-2 shrink-0 rounded-full min-[420px]:block"
          style={{ background: `var(${assetColorVar(asset)})` }}
          aria-hidden="true"
        />
        <span className="truncate text-[13px] font-medium @xl:text-sm">{shortName(asset)}</span>
      </span>
      <span className="mt-2.5 flex items-end justify-between gap-3">
        <span className="min-w-0">
          <span className="num block truncate text-[1.05rem] font-semibold tracking-tight @xl:text-xl">
            {market.price === undefined ? "–" : formatPrice(market.price)}
          </span>
          <Change value={market.sinceClose} className="mt-0.5 block text-xs @xl:text-sm" />
        </span>
        <span className="hidden h-10 w-24 shrink-0 @3xl:block @5xl:w-32">
          <Sparkline values={market.weekCloses} colorVar={assetColorVar(asset)} />
        </span>
      </span>
    </button>
  );
}

const PERIODS = ["Day", "Week", "Month", "Year"] as const;
const COMPARE_GRID =
  "grid grid-cols-4 gap-x-4 @4xl:grid-cols-[minmax(0,1.1fr)_repeat(4,5.5rem)_minmax(0,1.6fr)] @4xl:gap-x-6";

function CompareRow({ asset }: { asset: Asset }) {
  const market = useMarket(asset);
  const values = [market.sinceClose, market.week, market.month, market.year];
  return (
    <div className={`${COMPARE_GRID} items-center gap-y-3 border-b border-line py-4 last:border-b-0`}>
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
        {market.price !== undefined && (
          <span className="num ml-auto text-sm text-muted @4xl:hidden">{formatPrice(market.price)}</span>
        )}
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

export function Overview() {
  const assets = useAssets();
  const now = useNow(60_000);
  const primary = assets.data?.filter((a) => a.is_primary) ?? [];
  const [selected, setSelected] = useState<string>();
  const shown = primary.find((a) => a.slug === selected) ?? primary[0];
  const today = new Intl.DateTimeFormat("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(now);

  return (
    <div
      className="flex flex-col gap-5 @xl:gap-7"
      style={shown ? ({ "--tint": `var(${assetColorVar(shown)})` } as CSSProperties) : undefined}
    >
      <div className="aurora" aria-hidden="true" />

      <header className="rise flex items-baseline justify-between gap-4">
        <h1 className="title">Markets</h1>
        <p className="label text-right">
          {today} · {zoneLabel()}
        </p>
      </header>

      {assets.isError && <Message>Markets are unavailable right now.</Message>}

      {shown && (
        <>
          <div
            className="rise rise-2 grid gap-2.5 @xl:gap-4"
            style={{ gridTemplateColumns: `repeat(${primary.length}, minmax(0, 1fr))` }}
            role="group"
            aria-label="Choose a market"
          >
            {primary.map((asset) => (
              <MarketOption
                key={asset.slug}
                asset={asset}
                selected={asset.slug === shown.slug}
                onSelect={() => setSelected(asset.slug)}
              />
            ))}
          </div>

          <div className="rise rise-3">
            <MarketStage asset={shown} linkToAsset />
          </div>

          <BriefCard assets={assets.data ?? []} />
          <LatestSignals assets={assets.data ?? []} />

          <section className="glass px-5 pb-2 pt-5 @xl:px-7 @xl:pt-6">
            <div className={`${COMPARE_GRID} items-end border-b border-line pb-3`}>
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
            <p className="pb-4 pt-3 text-xs leading-relaxed text-faint">
              Day is the change since the previous close; week, month, and year compare with the
              daily close 7, 30, and 365 days ago. The range runs from the lowest to the highest
              price of the last 365 days, with the current price marked.
            </p>
          </section>
        </>
      )}
    </div>
  );
}
