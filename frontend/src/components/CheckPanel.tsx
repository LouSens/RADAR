import { useState } from "react";

import type { BuyCheck } from "../api/client";
import { useBuyCheck } from "../api/queries";
import { formatCount, formatMoney, formatPrice } from "../lib/format";
import { Caption, Message, Panel } from "./ui";

const percent = (fraction: number) => `${Math.abs(fraction * 100).toFixed(1)}%`;
const signed = (value: number) => `${value >= 0 ? "+" : "−"}${formatMoney(Math.abs(value))}`;

const HEADLINE: Record<BuyCheck["where"], string> = {
  high: "The price is high right now",
  middle: "The price is in the middle right now",
  low: "The price is low right now",
};
const DETAIL: Record<BuyCheck["where"], string> = {
  high: "It is near the top of where it has been this week and this month.",
  middle: "It is neither near the top nor near the bottom of this week and this month.",
  low: "It is near the bottom of where it has been this week and this month.",
};
const OUTCOME: Record<string, string> = {
  high: "When you bought near the week's top",
  middle: "When you bought around the middle",
  low: "When you bought near the week's bottom",
};

/** A line from the lowest to the highest price of a period, with a dot at today's price. */
function PlaceBar({ label, place }: { label: string; place: number }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span>{label}</span>
        <span className="num text-muted">{Math.round(place * 100)} out of 100</span>
      </div>
      <div
        className="relative mt-2 h-2 rounded-full bg-line"
        role="img"
        aria-label={`${label}: ${Math.round(place * 100)} out of 100, where 0 is the lowest price and 100 the highest`}
      >
        <span
          className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent"
          style={{ left: `${place * 100}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between text-xs text-faint">
        <span>Lowest</span>
        <span>Highest</span>
      </div>
    </div>
  );
}

const moved = (fraction: number) =>
  Math.abs(fraction) < 0.002
    ? "has barely moved"
    : `is ${fraction > 0 ? "up" : "down"} ${percent(fraction)}`;

export function CheckResult({ check }: { check: BuyCheck }) {
  const tone =
    check.where === "high" ? "text-alert" : check.where === "low" ? "text-calm" : "text-ink";
  const outcomes = check.outcomes.filter((o) => o.trades >= 5);
  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="num text-sm text-muted">
          {check.coin} · {formatPrice(check.price)}
        </p>
        <p className={`mt-1 text-xl font-semibold tracking-tight ${tone}`}>
          {HEADLINE[check.where]}
        </p>
        <p className="mt-1 text-sm text-muted">
          {DETAIL[check.where]} It {moved(check.move_day)} since yesterday and{" "}
          {moved(check.move_week)} over the week
          {check.below_high < -0.005
            ? `, and sits ${percent(check.below_high)} below its highest price of the last 3 months`
            : ""}
          .
        </p>
      </div>

      <div className="grid grid-cols-1 gap-5 @xl:grid-cols-3">
        <PlaceBar label="This week" place={check.place_week} />
        {check.place_month != null && <PlaceBar label="This month" place={check.place_month} />}
        {check.place_quarter != null && (
          <PlaceBar label="Last 3 months" place={check.place_quarter} />
        )}
      </div>

      {(check.habit_place != null || check.yours || outcomes.length > 0) && (
        <div className="well p-4">
          <h3 className="text-sm font-semibold tracking-tight">Your own record</h3>
          <ul className="mt-2 flex flex-col gap-2 text-sm text-muted">
            {check.habit_place != null && (
              <li>
                Across all your coins, you usually bought at{" "}
                <span className="num text-ink">
                  {Math.round(check.habit_place * 100)} out of 100
                </span>{" "}
                in the week. Today this coin is at{" "}
                <span className="num text-ink">{Math.round(check.place_week * 100)}</span>.
              </li>
            )}
            {outcomes.map((o) => (
              <li key={o.where}>
                {OUTCOME[o.where] ?? o.where} ({formatCount(o.trades)} times): a week later the
                price was {o.after_week >= 0 ? "up" : "down"}{" "}
                <span className={`num ${o.after_week >= 0 ? "text-calm" : "text-alert"}`}>
                  {percent(o.after_week)}
                </span>{" "}
                on average, and lower {Math.round(o.fell_share * 100)} times out of 100.
              </li>
            ))}
            {check.yours && (
              <li>
                {check.coin} itself: you bought it {formatCount(check.yours.purchases)} times and
                sold it {formatCount(check.yours.sales)}, and are{" "}
                <span className={`num ${check.yours.result >= 0 ? "text-calm" : "text-alert"}`}>
                  {signed(check.yours.result)}
                </span>{" "}
                on it so far.
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

/** Before you buy: is this price high or low against its own recent past? */
export function CheckPanel({ suggestions }: { suggestions: string[] }) {
  const [typed, setTyped] = useState("");
  const [coin, setCoin] = useState(suggestions[0] ?? "BTC");
  const check = useBuyCheck(coin);
  const pick = (name: string) => {
    const clean = name.trim().toUpperCase();
    if (clean) setCoin(clean);
  };
  return (
    <Panel id="check" title="Before you buy" headline="Is this price high or low right now?">
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          pick(typed);
        }}
      >
        <input
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          placeholder="Type a coin, like SOL"
          aria-label="Coin to check"
          className="num min-w-0 flex-1 rounded-xl border border-line bg-transparent px-3 py-2 text-sm uppercase outline-none focus:border-accent"
        />
        <button
          type="submit"
          className="press rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-[var(--accent-ink)]"
        >
          Check
        </button>
      </form>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => pick(name)}
            aria-pressed={coin === name}
            className={`press rounded-full border px-3 py-1.5 text-xs font-medium ${
              coin === name ? "border-accent text-ink" : "border-line text-muted hover:text-ink"
            }`}
          >
            {name}
          </button>
        ))}
      </div>

      {check.isPending && <Message>Looking at {coin}…</Message>}
      {check.data === null && (
        <Message>Binance has no price for {coin} against USDT. Check the spelling.</Message>
      )}
      {check.data && <CheckResult check={check.data} />}

      <Caption
        facts={[
          {
            label: "What it compares",
            value: "Today's price with the lowest and highest of each period",
          },
          { label: "Prices from", value: "Binance, hour by hour, read when you ask" },
          { label: "Your record", value: "Your own past purchases on Binance" },
        ]}
      >
        A low price can go lower and a high price can go higher: RADAR cannot tell which way it goes
        next. This shows where you are standing before you buy, so that it is a choice and not a
        habit.
      </Caption>
    </Panel>
  );
}
