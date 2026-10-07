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

/** A coin you hold now: what it is worth, what you paid, and how it stands. */
function HeldCard({ asset }: { asset: AssetRecord }) {
  const now = asset.standing;
  const open = asset.unrealised ?? 0;
  const paid = now.average_cost ?? 0;
  const change = paid > 0 && asset.price != null ? asset.price / paid - 1 : undefined;
  return (
    <article className="well p-4">
      <header className="flex items-baseline justify-between gap-3">
        <h4 className="font-semibold tracking-tight">{asset.asset}</h4>
        <span className="num text-sm text-muted">worth {formatMoney(asset.value ?? 0)}</span>
      </header>
      <p className={`num mt-1 text-[1.35rem] font-semibold tracking-tight ${tone(open)}`}>
        {signed(open)}
        {change !== undefined && (
          <span className="ml-2 text-sm font-medium">
            {change >= 0 ? "up" : "down"} {percent(change)}
          </span>
        )}
      </p>
      <dl className="mt-2">
        <StatRow label="Average price you paid">{formatPrice(paid)}</StatRow>
        {asset.price != null && <StatRow label="Price now">{formatPrice(asset.price)}</StatRow>}
        {now.sales > 0 && (
          <StatRow label="From earlier sales of it">
            <span className={tone(now.realised)}>{signed(now.realised)}</span>
          </StatRow>
        )}
      </dl>
    </article>
  );
}

/** A coin you traded and no longer hold: one line with how it ended. */
function PastRow({ asset }: { asset: AssetRecord }) {
  const now = asset.standing;
  const result = now.realised;
  return (
    <li className="flex items-baseline justify-between gap-3 border-t border-line py-2.5 first:border-t-0">
      <span className="min-w-0">
        <span className="font-medium">{asset.asset}</span>{" "}
        <span className="text-xs text-muted">
          bought {formatCount(now.purchases)}, sold {formatCount(now.sales)}
        </span>
      </span>
      <span className={`num shrink-0 font-medium ${tone(result)}`}>{signed(result)}</span>
    </li>
  );
}

/** What your trades have made or lost so far, and when you tend to buy and sell. */
export function RecordPanel({ record, worth }: { record: AccountRecord; worth?: number }) {
  const total = record.realised + record.unrealised;
  const held = record.assets.filter((a) => a.held);
  const past = record.assets
    .filter((a) => !a.held)
    .sort((a, b) => a.standing.realised - b.standing.realised);
  const results = record.assets.map(totalOf);
  const won = results.filter((r) => r > 0).reduce((sum, r) => sum + r, 0);
  const lost = results.filter((r) => r < 0).reduce((sum, r) => sum + r, 0);
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
        Every coin, all time: {formatCount(record.trades)} trades
        {record.first_trade ? ` since ${formatDate(record.first_trade)}` : ""}.
        {climb !== undefined &&
          ` To get it back from growth alone, everything you hold (${formatMoney(worth ?? 0)}) would have to rise ${percent(climb)}.`}
      </p>

      <div className="grid grid-cols-2 gap-3">
        <Figure label="Coins that made money" value={won} note="added together" />
        <Figure label="Coins that lost money" value={lost} note="added together" />
      </div>

      {record.moved_out_cost >= 1 && (
        <p className="text-sm text-muted">
          Not counted either way: coins you paid {formatMoney(record.moved_out_cost)} for left your
          trading wallet without a sale on record (moved, withdrawn, or swapped another way). If
          they were lost, your total is that much lower.
        </p>
      )}

      {held.length > 0 && (
        <div className="border-t border-line pt-5">
          <h3 className="text-sm font-semibold tracking-tight">Coins you hold now</h3>
          <div className="mt-3 grid grid-cols-1 gap-3 @xl:grid-cols-2 @4xl:grid-cols-3">
            {held.map((asset) => (
              <HeldCard key={asset.asset} asset={asset} />
            ))}
          </div>
        </div>
      )}

      {past.length > 0 && (
        <div className="border-t border-line pt-5">
          <h3 className="text-sm font-semibold tracking-tight">Coins you no longer hold</h3>
          <p className="mt-1 text-sm text-muted">How each ended. Biggest loss first.</p>
          <ul className="mt-2">
            {past.map((asset) => (
              <PastRow key={asset.asset} asset={asset} />
            ))}
          </ul>
        </div>
      )}

      <Timing record={record} />

      <Caption
        facts={[
          { label: "Where this comes from", value: "Your Binance trade history, read-only" },
          { label: "Fees", value: `${formatMoney(record.fees)} paid, already inside the totals` },
          {
            label: "Hold now",
            value: "Only what is really in your account and worth $1 or more",
          },
          {
            label: "Coins sent in from elsewhere",
            value: `Counted at that day's price, ${formatCount(record.priced_at_market)} times`,
          },
          {
            label: "A coin is missing?",
            value: "About 150 common coins are searched, plus any in your swaps and rewards",
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
