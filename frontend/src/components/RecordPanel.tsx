import type { AccountRecord } from "../api/client";
import { formatCount, formatMoney, formatPrice } from "../lib/format";
import { formatDate } from "../lib/time";
import { Caption, Panel, StatRow } from "./ui";

type AssetRecord = AccountRecord["assets"][number];
type Habit = NonNullable<AssetRecord["buys"]>;

const signed = (value: number) => `${value >= 0 ? "+" : "−"}${formatMoney(Math.abs(value))}`;
const tone = (value: number) =>
  value > 0.005 ? "text-calm" : value < -0.005 ? "text-alert" : "text-ink";
const percent = (fraction: number) =>
  `${fraction >= 0 ? "+" : "−"}${Math.abs(fraction * 100).toFixed(1)}%`;

/** Money-weighted average of one figure over every asset that has it. */
export function overall(
  assets: AssetRecord[],
  kind: "buys" | "sells",
  pick: (habit: Habit) => number,
): number | undefined {
  let total = 0;
  let weight = 0;
  for (const asset of assets) {
    const habit = asset[kind];
    if (!habit) continue;
    total += pick(habit) * habit.dollars;
    weight += habit.dollars;
  }
  return weight > 0 ? total / weight : undefined;
}

/** Where a kind of trade sat in the week's range, in words. */
export function placeWords(place: number): string {
  if (place >= 0.6) return "in the upper part of the week's range";
  if (place <= 0.4) return "in the lower part of the week's range";
  return "around the middle of the week's range";
}

function Figure({ label, value, note }: { label: string; value: number; note: string }) {
  return (
    <div className="well p-4">
      <p className="label">{label}</p>
      <p className={`num mt-1.5 text-[1.35rem] font-semibold tracking-tight ${tone(value)}`}>
        {signed(value)}
      </p>
      <p className="mt-0.5 text-sm text-muted">{note}</p>
    </div>
  );
}

/** A 0 to 1 track with a marker for the trades and a tick for any hour. */
function PlaceBar({ label, place, usual }: { label: string; place: number; usual?: number }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="text-muted">{label}</span>
        <span className="num text-ink">{Math.round(place * 100)}%</span>
      </div>
      <div
        className="relative mt-1.5 h-2 rounded-full bg-line"
        role="img"
        aria-label={`${label}: ${Math.round(place * 100)}% of the way from the week's low to its high`}
      >
        {usual !== undefined && (
          <span
            className="absolute top-[-3px] h-[14px] w-px bg-muted"
            style={{ left: `${usual * 100}%` }}
          />
        )}
        <span
          className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent"
          style={{ left: `${place * 100}%` }}
        />
      </div>
    </div>
  );
}

function Timing({ record }: { record: AccountRecord }) {
  const buys = overall(record.assets, "buys", (h) => h.place);
  const sells = overall(record.assets, "sells", (h) => h.place);
  const buysBefore = overall(record.assets, "buys", (h) => h.before_day);
  const sellsBefore = overall(record.assets, "sells", (h) => h.before_day);
  const usual = record.assets.find((a) => a.usual)?.usual?.place;
  if (buys === undefined || sells === undefined) return null;
  return (
    <div className="border-t border-line pt-5">
      <h3 className="text-sm font-semibold tracking-tight">When you bought and sold</h3>
      <p className="mt-1 text-sm text-muted">
        Your purchases were made {placeWords(buys)}
        {buysBefore !== undefined && `, after a day that had moved ${percent(buysBefore)}`}. Your
        sales were made {placeWords(sells)}
        {sellsBefore !== undefined && `, after a day that had moved ${percent(sellsBefore)}`}.
      </p>
      <div className="mt-4 grid grid-cols-1 gap-4 @xl:grid-cols-2">
        <PlaceBar label="Purchases" place={buys} usual={usual} />
        <PlaceBar label="Sales" place={sells} usual={usual} />
      </div>
      <p className="mt-2 text-xs text-faint">
        0% is the lowest price of the week before the trade, 100% the highest. The thin line is any
        hour.
      </p>
    </div>
  );
}

function AssetCard({ asset }: { asset: AssetRecord }) {
  const now = asset.standing;
  const flags = [
    asset.buys_unusual && asset.buys && `Bought ${placeWords(asset.buys.place)}`,
    asset.sells_unusual && asset.sells && `Sold ${placeWords(asset.sells.place)}`,
  ].filter(Boolean);
  return (
    <article className="well p-4">
      <header className="flex items-baseline justify-between gap-3">
        <h4 className="font-semibold tracking-tight">{asset.asset}</h4>
        <span className="num text-sm text-muted">
          {formatCount(now.purchases)} bought · {formatCount(now.sales)} sold
        </span>
      </header>
      <dl className="mt-2">
        {now.average_cost != null && now.units > 0 && (
          <StatRow label="Break-even price">{formatPrice(now.average_cost)}</StatRow>
        )}
        {asset.price != null && <StatRow label="Price now">{formatPrice(asset.price)}</StatRow>}
        <StatRow label="Gain taken by selling">
          <span className={tone(now.realised)}>{signed(now.realised)}</span>
        </StatRow>
        {asset.unrealised != null && now.units > 0 && (
          <StatRow label="Gain on what you hold">
            <span className={tone(asset.unrealised)}>{signed(asset.unrealised)}</span>
          </StatRow>
        )}
        {asset.compared && (
          <StatRow label="Against holding">
            <span className={tone(asset.compared.difference)}>
              {signed(asset.compared.difference)}
            </span>
          </StatRow>
        )}
      </dl>
      {flags.length > 0 && (
        <p className="mt-2 text-xs text-muted">{flags.join(" · ")}, more than chance would give.</p>
      )}
    </article>
  );
}

/** What the holdings cost, what was made, and how the trades were timed. */
export function RecordPanel({ record }: { record: AccountRecord }) {
  const difference = record.as_traded - record.if_held;
  const shown = record.assets.filter((a) => a.standing.purchases + a.standing.sales >= 2);
  return (
    <Panel
      id="record"
      title="Your record"
      headline={`${formatCount(record.trades)} trades${
        record.first_trade ? ` since ${formatDate(record.first_trade)}` : ""
      }`}
    >
      <div className="grid grid-cols-2 gap-3 @4xl:grid-cols-4">
        <Figure label="Gain taken" value={record.realised} note="from what you sold" />
        <Figure label="Gain still open" value={record.unrealised} note="on what you hold now" />
        <Figure
          label="Against holding"
          value={difference}
          note="same money, same days, never sold"
        />
        <Figure label="Fees" value={-record.fees} note="paid on trades" />
      </div>

      <Timing record={record} />

      <div className="border-t border-line pt-5">
        <h3 className="text-sm font-semibold tracking-tight">Asset by asset</h3>
        <div className="mt-3 grid grid-cols-1 gap-3 @xl:grid-cols-2 @4xl:grid-cols-3">
          {shown.map((asset) => (
            <AssetCard key={asset.asset} asset={asset} />
          ))}
        </div>
      </div>

      <Caption
        facts={[
          { label: "From", value: "Your Binance history, read with a read-only key" },
          { label: "Cost method", value: "Average of what was paid for the units still held" },
          {
            label: "Against holding",
            value: "New money put in at the same times and never sold, at today's price",
          },
          {
            label: "Priced at the market",
            value: `${formatCount(record.priced_at_market)} entries with no recorded price, such as coins sent in`,
          },
          { label: "Updated", value: `${formatDate(record.as_of)}, once a day` },
        ]}
      >
        This describes what happened. A habit is named only when it is further from any hour than
        chance would give, on ten trades or more. What prices did after past trades says nothing
        about the next one.
      </Caption>
    </Panel>
  );
}
