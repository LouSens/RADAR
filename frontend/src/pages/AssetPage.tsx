import type { CSSProperties } from "react";
import { Navigate, useParams } from "react-router-dom";

import { useMarket } from "../api/market";
import { useAssets, useSummary } from "../api/queries";
import { DriversPanel } from "../components/DriversPanel";
import { MarketStage } from "../components/MarketStage";
import { NewsPanel } from "../components/NewsPanel";
import { OutlookPanel } from "../components/OutlookPanel";
import { RegimePanel } from "../components/RegimePanel";
import { RiskPanel } from "../components/RiskPanel";
import { SummaryCard } from "../components/SummaryCard";
import { PageSkeleton } from "../components/Skeleton";
import { SectionMenu, Tabs } from "../components/Tabs";
import { TrackRecordPanel } from "../components/TrackRecordPanel";
import { VolatilityPanel } from "../components/VolatilityPanel";
import { Change, Message, RangeBar, StatRow, assetColorVar, shortName } from "../components/ui";
import { formatPrice } from "../lib/format";
import { SECTIONS, isSection } from "../lib/sections";
import { formatDate } from "../lib/time";

export function AssetPage() {
  const { slug, section } = useParams();
  const assets = useAssets();
  const asset = assets.data?.find((a) => a.slug === slug);
  const market = useMarket(asset);
  const summary = useSummary(asset?.slug).data ?? undefined;
  const trust = summary?.trust;

  if (assets.isPending) return <PageSkeleton cards={3} />;
  if (!asset) return <Message>That market could not be found.</Message>;

  const price = (value: number | undefined) => (value === undefined ? "–" : formatPrice(value));

  if (!isSection(section)) return <Navigate to={`/asset/${asset.slug}`} replace />;
  const base = `/asset/${asset.slug}`;

  return (
    <div
      className="flex flex-col gap-4 @xl:gap-6"
      style={{ "--tint": `var(${assetColorVar(asset)})` } as CSSProperties}
    >
      <div className="aurora" aria-hidden="true" />

      <header className="flex items-baseline gap-3">
        <h1 className="title">{shortName(asset)}</h1>
        <span className="label">{asset.symbol}</span>
      </header>

      <Tabs
        base={base}
        items={SECTIONS}
        label={`${shortName(asset)} pages`}
        parent={shortName(asset)}
        up={{ to: "/markets", label: "Markets" }}
      />

      {section === undefined || section === "" ? (
        <>
          <div className="rise">
            <MarketStage key={asset.slug} asset={asset} allowCandles />
          </div>
          {summary && <SummaryCard asset={asset} summary={summary} />}
          <SectionMenu base={base} items={SECTIONS} title="Look closer" />
          <section className="glass rise rise-2 grid grid-cols-1 gap-x-12 gap-y-6 p-4 @xl:p-7 @4xl:grid-cols-2">
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
        </>
      ) : (
        <div className="section-body" key={`${asset.slug}-${section}`}>
          {section === "state" && <RegimePanel asset={asset} trust={trust?.state} />}
          {section === "outlook" && <OutlookPanel asset={asset} trust={trust?.outlook} />}
          {section === "swings" && <VolatilityPanel asset={asset} trust={trust?.swings} />}
          {section === "risk" && <RiskPanel asset={asset} trust={trust?.risk} />}
          {section === "drivers" && <DriversPanel asset={asset} />}
          {section === "news" && <NewsPanel asset={asset} trust={trust?.news} />}
          {section === "record" && <TrackRecordPanel asset={asset} />}
        </div>
      )}
    </div>
  );
}
