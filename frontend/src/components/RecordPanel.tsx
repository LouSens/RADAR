import type { AccountRecord } from "../api/client";
import { formatCount, formatMoney, formatPrice } from "../lib/format";
import { formatDate } from "../lib/time";
import { Caption, Panel, StatRow } from "./ui";

type AssetRecord = AccountRecord["assets"][number];
type Habit = NonNullable<AssetRecord["buys"]>;

const signed = (value: number) => `${value >= 0 ? "+" : "−"}${formatMoney(Math.abs(value))}`;
const tone = (value: number) =>
  value > 0.005 ? "text-calm" : value < -0.005 ? "text-alert" : "text-ink";
const percent = (fraction: number) => `${Math.abs(fraction * 100).toFixed(1)}%`;

/** Money-weighted average of one figure over every coin that has it. */
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

/** What one coin has made or lost in all: what was sold, plus what is still held. */
export const totalOf = (asset: AssetRecord) => asset.standing.realised + (asset.unrealised ?? 0);

/** Where a price sat in its week, in plain words. */
export function placeWords(place: number): string {
  if (place >= 0.6) return "near the highest price of that week";
  if (place <= 0.4) return "near the lowest price of that week";
  return "around the middle of that week's prices";
}

const moved = (fraction: number) =>
  Math.abs(fraction) < 0.002
    ? "had barely moved"
    : `had ${fraction > 0 ? "risen" : "fallen"} ${percent(fraction)}`;

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

/** A line from the week's cheapest price to its dearest, with a dot where you traded. */
function PlaceBar({ label, place, usual }: { label: string; place: number; usual?: number }) {
  return (
    <div>
      <p className="text-sm text-muted">{label}</p>
      <div
        className="relative mt-2 h-2 rounded-full bg-line"
        role="img"
        aria-label={`${label}: ${Math.round(place * 100)} out of 100, where 0 is the week's cheapest price and 100 its most expensive`}
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
      <div className="mt-1 flex justify-between text-xs text-faint">
        <span>Cheapest that week</span>
        <span>Most expensive</span>
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
      <h3 className="text-sm font-semibold tracking-tight">When you usually buy and sell</h3>
      <div className="mt-3 grid grid-cols-1 gap-5 @xl:grid-cols-2">
        <div>
          <p className="text-sm">
            You usually bought {placeWords(buys)}
            {buysBefore !== undefined && `, when the price ${moved(buysBefore)} in the day before`}.
          </p>
          <div className="mt-3">
            <PlaceBar label="The price you paid" place={buys} usual={usual} />
          </div>
        </div>
        <div>
          <p className="text-sm">
            You usually sold {placeWords(sells)}
            {sellsBefore !== undefined &&
              `, when the price ${moved(sellsBefore)} in the day before`}
            .
          </p>
          <div className="mt-3">
            <PlaceBar label="The price you got" place={sells} usual={usual} />
          </div>
        </div>
      </div>
      {buys > sells + 0.1 && (
        <p className="mt-4 text-sm text-muted">
          Buying nearer the top and selling nearer the bottom is how trades end in a loss.
        </p>
      )}
    </div>
  );
}

function AssetCard({ asset }: { asset: AssetRecord }) {
  const now = asset.standing;
  // Crumbs left by fees are not a holding worth a line.
  const holding = now.average_cost != null && (asset.value ?? 0) >= 0.01;
  const total = totalOf(asset);
  const habits = [
    asset.buys_unusual && asset.buys && `You usually bought it ${placeWords(asset.buys.place)}.`,
    asset.sells_unusual && asset.sells && `You usually sold it ${placeWords(asset.sells.place)}.`,
  ].filter((line) => line && !line.includes("middle"));
  return (
    <article className="well p-4">
      <header className="flex items-baseline justify-between gap-3">
        <h4 className="font-semibold tracking-tight">{asset.asset}</h4>
        <span className={`num font-semibold ${tone(total)}`}>{signed(total)}</span>
      </header>
      <p className="text-xs text-muted">
        Bought {formatCount(now.purchases)} {now.purchases === 1 ? "time" : "times"}, sold{" "}
        {formatCount(now.sales)}
      </p>
      <dl className="mt-2">
        <StatRow label="On what you sold">
          <span className={tone(now.realised)}>{signed(now.realised)}</span>
        </StatRow>
        {holding && asset.unrealised != null && (
          <StatRow label="On what you still have">
            <span className={tone(asset.unrealised)}>{signed(asset.unrealised)}</span>
          </StatRow>
        )}
        {holding && now.average_cost != null && (
          <StatRow label="You are back to zero at">{formatPrice(now.average_cost)}</StatRow>
        )}
        {holding && asset.price != null && (
          <StatRow label="Price now">{formatPrice(asset.price)}</StatRow>
        )}
      </dl>
      {habits.length > 0 && <p className="mt-2 text-xs text-muted">{habits.join(" ")}</p>}
    </article>
  );
}

/** What your trades have made or lost so far, and when you tend to buy and sell. */
export function RecordPanel({ record, worth }: { record: AccountRecord; worth?: number }) {
  const total = record.realised + record.unrealised;
  const difference = record.as_traded - record.if_held;
  const coins = [...record.assets].sort((a, b) => totalOf(a) - totalOf(b));
  const climb = worth && worth > 0 && total < 0 ? -total / worth : undefined;
  return (
    <Panel
      id="record"
      title="Your trades so far"
      headline={
        total < 0
          ? `You are down ${formatMoney(-total)} in total`
          : `You are up ${formatMoney(total)} in total`
      }
    >
      <p className="text-sm text-muted">
        From {formatCount(record.trades)} trades
        {record.first_trade ? ` since ${formatDate(record.first_trade)}` : ""}.
        {climb !== undefined &&
          ` To get it back from growth alone, everything you hold (${formatMoney(worth ?? 0)}) would have to rise ${percent(climb)}.`}
      </p>

      <div className="grid grid-cols-2 gap-3 @4xl:grid-cols-4">
        <Figure
          label="On coins you sold"
          value={record.realised}
          note="Final: these trades are closed"
        />
        <Figure
          label="On coins you still have"
          value={record.unrealised}
          note="Changes as prices move"
        />
        <Figure label="Fees you paid" value={-record.fees} note="Already counted in the totals" />
        <Figure
          label="Versus buying and keeping"
          value={difference}
          note={
            difference >= 0
              ? "Your selling left you better off than never selling"
              : "Never selling would have left you better off"
          }
        />
      </div>

      <Timing record={record} />

      <div className="border-t border-line pt-5">
        <h3 className="text-sm font-semibold tracking-tight">Coin by coin</h3>
        <p className="mt-1 text-sm text-muted">Biggest loss first.</p>
        <div className="mt-3 grid grid-cols-1 gap-3 @xl:grid-cols-2 @4xl:grid-cols-3">
          {coins.map((asset) => (
            <AssetCard key={asset.asset} asset={asset} />
          ))}
        </div>
      </div>

      <Caption
        facts={[
          { label: "Where this comes from", value: "Your Binance trade history, read-only" },
          {
            label: "Back to zero at",
            value: "The average price you paid for the coins you still have",
          },
          {
            label: "Versus buying and keeping",
            value: "The same money put in on the same days and never sold, at today's prices",
          },
          {
            label: "Coins sent in from elsewhere",
            value: `Counted at that day's price, ${formatCount(record.priced_at_market)} times`,
          },
          {
            label: "A coin is missing?",
            value:
              "Only coins found in your swaps, rewards, holdings and a short list are searched",
          },
          { label: "Updated", value: `${formatDate(record.as_of)}, once a day` },
        ]}
      >
        This shows what has happened. It does not tell you what to do next, and what prices did
        after your past trades says nothing about the next one.
      </Caption>
    </Panel>
  );
}
