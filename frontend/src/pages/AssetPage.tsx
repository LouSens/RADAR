import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import type { Timeframe } from "../api/client";
import { useAssets, useBars } from "../api/queries";
import { LivePriceTag, useFreshPrice } from "../components/LivePriceTag";
import { PriceChart } from "../components/PriceChart";
import { Caption, Notice, Panel, SectionLabel, Stat, assetColorVar } from "../components/ui";
import { formatCount, formatPrice } from "../lib/format";
import { formatDate, zoneLabel } from "../lib/time";

const LIMIT = 500;
const TIMEFRAMES: { value: Timeframe; label: string }[] = [
  { value: "1Hour", label: "Hourly" },
  { value: "1Day", label: "Daily" },
];
const TABS = [
  ["Regime", "What state the market is in, and how long such states last.", "Phase 3"],
  ["Outlook", "The simulated range of outcomes, volatility forecast, and tail risk.", "Phase 3"],
  ["News", "News tone, topics, and whether news has moved price.", "Phase 4"],
  ["Drivers", "Which outside forces this asset is moving with.", "Phase 5"],
] as const;

export function AssetPage() {
  const { slug } = useParams();
  const [timeframe, setTimeframe] = useState<Timeframe>("1Hour");
  const assets = useAssets();
  const asset = assets.data?.find((a) => a.slug === slug);
  const bars = useBars(asset?.slug, timeframe, LIMIT);
  // The header price always comes from hourly bars, whatever the chart shows.
  const hourly = useBars(asset?.slug, "1Hour", 1);
  const live = useFreshPrice(asset?.symbol);

  if (assets.isPending) return <Notice>Loading…</Notice>;
  if (!asset) return <Notice>RADAR has no asset called “{slug}”.</Notice>;

  const rows = bars.data?.bars ?? [];
  const first = rows[0];
  const last = rows.at(-1);
  const source =
    bars.data?.source === "sip"
      ? "US consolidated feed, 15 minutes delayed"
      : bars.data?.source
        ? `Kraken (${bars.data.source}) through Alpaca`
        : "";

  return (
    <div className="flex flex-col gap-10">
      <header className="rise flex flex-wrap items-end justify-between gap-x-8 gap-y-5">
        <div>
          <Link to="/" className="text-xs text-muted hover:text-ink">
            ← Overview
          </Link>
          <h1 className="display text-fluid-h2 mt-2">{asset.name}</h1>
          <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: `var(${assetColorVar(asset)})` }}
              aria-hidden="true"
            />
            <span className="num">{asset.symbol}</span>
            <span aria-hidden="true">·</span>
            {asset.trades_continuously ? "trades around the clock" : "trades in US market hours only"}
          </p>
        </div>
        <LivePriceTag asset={asset} lastBar={hourly.data?.bars.at(-1)} size="lg" align="left" />
      </header>

      <Panel
        className="rise rise-2"
        title="Price"
        aside={
          <div
            className="inline-flex rounded-full border border-line-strong bg-white/[0.03] p-0.5"
            role="group"
            aria-label="Bar size"
          >
            {TIMEFRAMES.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={timeframe === option.value}
                onClick={() => setTimeframe(option.value)}
                className={`rounded-full px-3.5 py-1 text-xs font-medium transition-colors ${
                  timeframe === option.value ? "bg-accent text-accent-ink" : "text-muted hover:text-ink"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        }
      >
        {bars.isPending && <Notice>Loading prices…</Notice>}
        {bars.isError && <Notice>Prices could not be loaded. Is the API running?</Notice>}
        {bars.isSuccess && rows.length === 0 && <Notice>No prices stored for this asset yet.</Notice>}
        {rows.length > 0 && first && last && (
          <>
            <div className="h-[280px] sm:h-[400px]">
              <PriceChart
                key={timeframe}
                bars={rows}
                timeframe={timeframe}
                assetClass={asset.asset_class}
                kind="candles"
                colorVar={assetColorVar(asset)}
                live={live}
                height="100%"
                label={`${asset.name} ${timeframe === "1Hour" ? "hourly" : "daily"} price candles`}
              />
            </div>
            <Caption>
              {timeframe === "1Hour" ? "Hourly" : "Daily"} open, high, low, and close,{" "}
              {formatDate(first.ts)} to {formatDate(last.ts)} ({zoneLabel()}), n ={" "}
              {formatCount(rows.length)} bars. Source: {source}.
              {live ? " The last candle is still forming and is drawn from the live feed." : ""}
            </Caption>
            <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat label="Highest in window" value={formatPrice(Math.max(...rows.map((b) => b.high)))} />
              <Stat label="Lowest in window" value={formatPrice(Math.min(...rows.map((b) => b.low)))} />
              <Stat label="Last stored close" value={formatPrice(last.close)} />
              <Stat
                label="Bars with no trades"
                value={formatCount(rows.filter((b) => b.is_quote_only).length)}
              />
            </div>
          </>
        )}
      </Panel>

      <section>
        <SectionLabel aside="not built yet">Analysis</SectionLabel>
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {TABS.map(([name, what, phase]) => (
            <li key={name} className="well flex flex-col gap-2 p-4">
              <span className="num text-[11px] uppercase tracking-wider text-accent">{phase}</span>
              <span className="font-semibold leading-tight">{name}</span>
              <span className="text-sm leading-snug text-muted">{what}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
