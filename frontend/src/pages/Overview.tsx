import { Link } from "react-router-dom";

import type { Asset } from "../api/client";
import { useAssets, useBars } from "../api/queries";
import { LiveBadge, LivePriceTag, useFreshPrice } from "../components/LivePriceTag";
import { PriceChart } from "../components/PriceChart";
import { Caption, Notice, Panel, SectionLabel, assetColorVar, shortName } from "../components/ui";
import { formatChange, formatCount, formatPrice } from "../lib/format";
import { formatDate, zoneLabel } from "../lib/time";

const WINDOW_BARS = 168;

/** Latest price and the change across the window shown, from stored bars plus the live feed. */
function useSnapshot(asset: Asset) {
  const bars = useBars(asset.slug, "1Hour", WINDOW_BARS);
  const live = useFreshPrice(asset.symbol);
  const rows = bars.data?.bars ?? [];
  const first = rows[0];
  const last = rows.at(-1);
  const latest = live?.price ?? last?.close;
  const change = first && latest !== undefined ? latest / first.close - 1 : undefined;
  return { bars, live, rows, first, last, latest, change };
}

function TickerRow({ asset }: { asset: Asset }) {
  const { live, latest, change } = useSnapshot(asset);
  return (
    <Link
      to={`/asset/${asset.slug}`}
      className="flex items-center justify-between gap-4 rounded-2xl px-4 py-3 transition-colors hover:bg-white/[0.05]"
    >
      <span className="flex items-center gap-3">
        <span
          className="h-8 w-1 rounded-full"
          style={{ background: `var(${assetColorVar(asset)})` }}
          aria-hidden="true"
        />
        <span>
          <span className="block font-semibold leading-tight">{shortName(asset)}</span>
          <span className="block text-xs text-muted">{asset.symbol}</span>
        </span>
      </span>
      <span className="text-right">
        <span className="num block text-lg font-semibold leading-tight">
          {latest === undefined ? "–" : formatPrice(latest)}
        </span>
        <span className="flex items-center justify-end gap-2 text-xs">
          {change !== undefined && (
            <span className={`num ${change >= 0 ? "text-calm" : "text-alert"}`}>
              {formatChange(change)}
            </span>
          )}
          {live ? <LiveBadge /> : <span className="text-faint">not live</span>}
        </span>
      </span>
    </Link>
  );
}

function AssetCard({ asset }: { asset: Asset }) {
  const { bars, live, rows, first, last, change } = useSnapshot(asset);
  return (
    <Panel lift className="flex flex-col">
      <div className="mb-4 flex flex-col gap-3">
        <div className="flex items-baseline justify-between gap-3">
          <Link to={`/asset/${asset.slug}`} className="text-lg font-semibold tracking-tight hover:text-accent">
            {shortName(asset)}
          </Link>
          <span className="num text-xs text-muted">{asset.symbol}</span>
        </div>
        <div className="flex items-end justify-between gap-3">
          <LivePriceTag asset={asset} lastBar={last} align="left" />
          {change !== undefined && (
            <div className="text-right text-xs text-muted">
              <div className={`num text-sm ${change >= 0 ? "text-calm" : "text-alert"}`}>
                {formatChange(change)}
              </div>
              over the window shown
            </div>
          )}
        </div>
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
            height={210}
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
  ["Market regime", "Calm, normal, or turbulent, with how sure the model is.", "Phase 3"],
  ["Outlook", "The plausible price range, simulated 10,000 times, with its track record.", "Phase 3"],
  ["News", "The tone of the news, and whether it has actually moved price.", "Phase 4"],
  ["Portfolio", "Where your risk comes from, and other ways to split the same money.", "Phase 5"],
  ["Signals and brief", "What changed today, and how reliable that kind of change has been.", "Phase 6"],
] as const;

export function Overview() {
  const assets = useAssets();
  const primary = assets.data?.filter((a) => a.is_primary) ?? [];
  const lead = primary[0];

  return (
    <div className="flex flex-col gap-14 sm:gap-20">
      <section className="relative grid items-center gap-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <div className="radar -right-24 -top-24 hidden w-[34rem] opacity-70 lg:block" aria-hidden="true" />
        <div className="rise relative">
          <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-line-strong bg-white/[0.03] px-3 py-1 text-xs text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
            Market analytics, not advice
          </p>
          <h1 className="display text-fluid-h1">
            Know what kind of market <span className="text-accent">you are in.</span>
          </h1>
          <p className="mt-5 max-w-[56ch] text-base text-muted sm:text-lg">
            RADAR reads Bitcoin, gold, and US stocks the way a risk desk would: the current regime,
            the realistic range of outcomes, and what the news has measurably done to price. Every
            number comes with its track record.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            {lead && (
              <Link to={`/asset/${lead.slug}`} className="btn btn-primary">
                Open {shortName(lead)}
              </Link>
            )}
            <Link to="/status" className="btn btn-ghost">
              See data coverage
            </Link>
          </div>
        </div>
        <div className="glass rise rise-2 relative p-2">
          <div className="px-4 pb-1 pt-3 text-xs text-muted">Now · change over the last 7 days of bars</div>
          {assets.isError && (
            <div className="p-2">
              <Notice>The asset list could not be loaded. Is the API running?</Notice>
            </div>
          )}
          {assets.isPending && (
            <div className="p-2">
              <Notice>Loading…</Notice>
            </div>
          )}
          {primary.map((asset) => (
            <TickerRow key={asset.slug} asset={asset} />
          ))}
        </div>
      </section>

      <section>
        <SectionLabel aside={`${primary.length} assets analysed in full`}>Markets</SectionLabel>
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {primary.map((asset) => (
            <AssetCard key={asset.slug} asset={asset} />
          ))}
        </div>
      </section>

      <section>
        <SectionLabel aside="in build order">Not built yet</SectionLabel>
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {COMING.map(([name, what, phase]) => (
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
