import { useState } from "react";
import { useParams } from "react-router-dom";

import type { Timeframe } from "../api/client";
import { useAssets, useBars } from "../api/queries";
import { LivePriceTag, useFreshPrice } from "../components/LivePriceTag";
import { PriceChart } from "../components/PriceChart";
import { Caption, Notice, Panel, assetColorVar } from "../components/ui";
import { formatCount, formatPrice } from "../lib/format";
import { formatDate, zoneLabel } from "../lib/time";

const LIMIT = 500;
const TIMEFRAMES: { value: Timeframe; label: string }[] = [
  { value: "1Hour", label: "Hourly" },
  { value: "1Day", label: "Daily" },
];
const TABS = [
  ["Regime", "Phase 3"],
  ["Outlook", "Phase 3"],
  ["News", "Phase 4"],
  ["Drivers", "Phase 5"],
] as const;

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-raised px-3 py-2">
      <div className="text-xs text-muted">{label}</div>
      <div className="num">{value}</div>
    </div>
  );
}

export function AssetPage() {
  const { slug } = useParams();
  const [timeframe, setTimeframe] = useState<Timeframe>("1Hour");
  const assets = useAssets();
  const asset = assets.data?.find((a) => a.slug === slug);
  const bars = useBars(asset?.slug, timeframe, LIMIT);
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
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{asset.name}</h1>
          <p className="text-muted">
            {asset.symbol} ·{" "}
            {asset.trades_continuously
              ? "trades around the clock"
              : "trades in US market hours only"}
          </p>
        </div>
        <LivePriceTag asset={asset} lastBar={timeframe === "1Hour" ? last : undefined} />
      </header>

      <Panel
        title="Price"
        aside={
          <div className="inline-flex overflow-hidden rounded-md border border-line" role="group" aria-label="Bar size">
            {TIMEFRAMES.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={timeframe === option.value}
                onClick={() => setTimeframe(option.value)}
                className={`px-3 py-1 text-xs ${
                  timeframe === option.value ? "bg-accent text-panel" : "text-muted hover:text-ink"
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
            <PriceChart
              key={timeframe}
              bars={rows}
              timeframe={timeframe}
              assetClass={asset.asset_class}
              kind="candles"
              colorVar={assetColorVar(asset)}
              live={live}
              height={380}
              label={`${asset.name} ${timeframe === "1Hour" ? "hourly" : "daily"} price candles`}
            />
            <Caption>
              {timeframe === "1Hour" ? "Hourly" : "Daily"} open, high, low, and close,{" "}
              {formatDate(first.ts)} to {formatDate(last.ts)} ({zoneLabel()}), n ={" "}
              {formatCount(rows.length)} bars. Source: {source}.
              {live ? " The last candle is still forming and is drawn from the live feed." : ""}
            </Caption>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
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

      <Panel title="Analysis">
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {TABS.map(([name, phase]) => (
            <li key={name} className="rounded-md border border-dashed border-line px-3 py-2">
              <div className="font-medium">{name}</div>
              <div className="text-xs text-muted">Not built yet · {phase}</div>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
