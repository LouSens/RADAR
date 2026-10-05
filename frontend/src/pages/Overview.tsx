import { Link } from "react-router-dom";

import type { Asset } from "../api/client";
import { useAssets, useBars } from "../api/queries";
import { LivePriceTag, useFreshPrice } from "../components/LivePriceTag";
import { PriceChart } from "../components/PriceChart";
import { Caption, Notice, Panel, assetColorVar } from "../components/ui";
import { formatChange, formatCount } from "../lib/format";
import { formatDate, zoneLabel } from "../lib/time";

const WINDOW_BARS = 168;

function AssetCard({ asset }: { asset: Asset }) {
  const bars = useBars(asset.slug, "1Hour", WINDOW_BARS);
  const live = useFreshPrice(asset.symbol);
  const rows = bars.data?.bars ?? [];
  const first = rows[0];
  const last = rows.at(-1);
  const latest = live?.price ?? last?.close;
  const change = first && latest !== undefined ? latest / first.close - 1 : undefined;

  return (
    <Panel
      title={
        <Link to={`/asset/${asset.slug}`} className="hover:text-accent">
          {asset.name} <span className="font-normal text-muted">{asset.symbol}</span>
        </Link>
      }
    >
      <div className="mb-2 flex items-end justify-between gap-3">
        <div className="text-sm">
          {change !== undefined && (
            <>
              <span className={`num ${change >= 0 ? "text-calm" : "text-alert"}`}>
                {formatChange(change)}
              </span>
              <span className="text-muted"> over the window shown</span>
            </>
          )}
        </div>
        <LivePriceTag asset={asset} lastBar={last} />
      </div>
      {bars.isPending && <Notice>Loading prices…</Notice>}
      {bars.isError && <Notice>Prices could not be loaded. Is the API running?</Notice>}
      {bars.isSuccess && rows.length === 0 && (
        <Notice>No prices stored for this asset yet. Run the backfill.</Notice>
      )}
      {rows.length > 0 && first && last && (
        <>
          <PriceChart
            bars={rows}
            timeframe="1Hour"
            assetClass={asset.asset_class}
            kind="area"
            colorVar={assetColorVar(asset)}
            live={live}
            height={200}
            label={`${asset.name} hourly closing prices`}
          />
          <Caption>
            Hourly closing prices, {formatDate(first.ts)} to {formatDate(last.ts)} ({zoneLabel()}),
            n = {formatCount(rows.length)} bars
            {asset.trades_continuously ? "" : ", including pre-market and after-hours trading"}.
          </Caption>
        </>
      )}
    </Panel>
  );
}

const COMING = [
  ["Market regime", "Calm, normal, or turbulent, with how sure the model is", "Phase 3"],
  ["Outlook", "The plausible price range, simulated, with its track record", "Phase 3"],
  ["News", "Tone of the news and whether it has moved price", "Phase 4"],
  ["Portfolio", "Where your risk comes from, and other ways to split it", "Phase 5"],
  ["Signals and brief", "What changed today and how reliable that has been", "Phase 6"],
] as const;

export function Overview() {
  const assets = useAssets();
  const primary = assets.data?.filter((a) => a.is_primary) ?? [];
  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-semibold">Overview</h1>
        <p className="max-w-[68ch] text-muted">
          Prices for the assets RADAR analyses in full. Regimes, outlooks, news, and signals join
          this screen as each is built.
        </p>
      </header>
      {assets.isError && <Notice>The asset list could not be loaded. Is the API running?</Notice>}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {primary.map((asset) => (
          <AssetCard key={asset.slug} asset={asset} />
        ))}
      </div>
      <Panel title="Not built yet">
        <ul className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
          {COMING.map(([name, what, phase]) => (
            <li key={name} className="flex items-baseline justify-between gap-3 border-b border-line pb-2">
              <span>
                <span className="font-medium">{name}.</span> <span className="text-muted">{what}</span>
              </span>
              <span className="num shrink-0 text-xs text-muted">{phase}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
