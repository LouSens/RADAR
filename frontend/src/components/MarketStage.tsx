import { useState } from "react";
import { Link } from "react-router-dom";

import type { Asset, Timeframe } from "../api/client";
import { useMarket } from "../api/market";
import { useBarsSince } from "../api/queries";
import { formatCount, formatPrice } from "../lib/format";
import { formatDate, zoneLabel } from "../lib/time";
import { Freshness } from "./PriceLine";
import { PriceChart } from "./PriceChart";
import { ChangeChip, Segmented, assetColorVar, shortName } from "./ui";

const RANGES = [
  { value: "1W", label: "1W", timeframe: "1Hour", days: 7, words: "Hourly" },
  { value: "1M", label: "1M", timeframe: "1Hour", days: 30, words: "Hourly" },
  { value: "3M", label: "3M", timeframe: "1Day", days: 92, words: "Daily" },
  { value: "1Y", label: "1Y", timeframe: "1Day", days: 366, words: "Daily" },
  { value: "ALL", label: "All", timeframe: "1Day", days: 4000, words: "Daily" },
] as const satisfies readonly {
  value: string;
  label: string;
  timeframe: Timeframe;
  days: number;
  words: string;
}[];

type RangeKey = (typeof RANGES)[number]["value"];
type Kind = "area" | "candles";

const KINDS = [
  { value: "area", label: "Line" },
  { value: "candles", label: "Candles" },
] as const;

/**
 * The main surface for one market: its price, how it has moved, and the chart, as a
 * single piece. The chart runs to the edges of the surface.
 */
export function MarketStage({
  asset,
  allowCandles = false,
  linkToAsset = false,
}: {
  asset: Asset;
  allowCandles?: boolean;
  linkToAsset?: boolean;
}) {
  const [rangeKey, setRangeKey] = useState<RangeKey>("1W");
  const [kind, setKind] = useState<Kind>("area");
  const range = RANGES.find((r) => r.value === rangeKey) ?? RANGES[0];
  const bars = useBarsSince(asset.slug, range.timeframe, range.days);
  const market = useMarket(asset);
  const rows = bars.data?.bars ?? [];
  const first = rows[0];
  const last = rows.at(-1);
  const suspect = rows.filter((bar) => bar.is_outlier).length;
  const source = asset.asset_class === "stock" ? "US exchanges, 15 minutes delayed" : "Kraken";

  return (
    <section className="glass stage">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4 p-5 pb-3 @xl:p-7 @xl:pb-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5 text-sm">
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: `var(${assetColorVar(asset)})` }}
              aria-hidden="true"
            />
            <span className="font-medium">{asset.name}</span>
            <span className="text-faint">{asset.symbol}</span>
          </div>
          <div className="num price-xl mt-3">
            {market.price === undefined ? "–" : formatPrice(market.price)}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <ChangeChip value={market.sinceClose} />
            <Freshness live={market.live !== undefined} asOf={market.asOf} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {allowCandles && (
            <Segmented options={KINDS} value={kind} onChange={setKind} label="Chart type" />
          )}
          <Segmented options={RANGES} value={rangeKey} onChange={setRangeKey} label="Time range" />
        </div>
      </div>

      <div className="stage-chart">
        {bars.isPending && <div className="grid h-full place-items-center text-sm text-faint">Loading…</div>}
        {bars.isError && (
          <div className="grid h-full place-items-center text-sm text-muted">
            Prices are unavailable right now.
          </div>
        )}
        {bars.isSuccess && rows.length === 0 && (
          <div className="grid h-full place-items-center text-sm text-muted">No prices for this period.</div>
        )}
        {rows.length > 0 && (
          <PriceChart
            key={`${asset.slug}-${range.timeframe}-${kind}`}
            bars={rows}
            timeframe={range.timeframe}
            assetClass={asset.asset_class}
            kind={kind}
            colorVar={assetColorVar(asset)}
            live={market.live}
            height="100%"
            label={`${asset.name} price, ${range.words.toLowerCase()} bars`}
          />
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 px-5 py-3.5 text-xs text-faint @xl:px-7">
        <p>
          {first && last ? (
            <>
              {range.words} {kind === "candles" ? "open, high, low, close" : "closes"} ·{" "}
              {formatDate(first.ts)} to {formatDate(last.ts)} · {formatCount(rows.length)} bars ·{" "}
              {zoneLabel()} · {source}
              {kind === "candles" && suspect > 0
                ? ` · ${suspect} bar${suspect === 1 ? "" : "s"} with a suspect high or low drawn without wicks`
                : ""}
            </>
          ) : (
            <>&nbsp;</>
          )}
        </p>
        {linkToAsset && (
          <Link to={`/asset/${asset.slug}`} className="font-medium text-muted transition-colors hover:text-ink">
            More on {shortName(asset)} <span aria-hidden="true">→</span>
          </Link>
        )}
      </div>
    </section>
  );
}
