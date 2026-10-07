import { Link } from "react-router-dom";

import type { Steps } from "../api/client";
import { formatMoney, formatPrice } from "../lib/format";
import { formatDate } from "../lib/time";
import { Caption, Message, Panel } from "./ui";

type Step = Steps["steps"][number];

const percent = (fraction: number, digits = 1) => `${Math.abs(fraction * 100).toFixed(digits)}%`;
const share = (fraction: number) => `${Math.round(fraction * 100)}%`;
const shortName = (name: string) => name.split(" (")[0] ?? name;

/** Where a price sits between the lowest and highest of the last three months. */
export function placeWords(place: number): string {
  if (place >= 0.8) return "near its highest price of the last 3 months";
  if (place >= 0.6) return "in the upper part of its last 3 months";
  if (place > 0.4) return "around the middle of its last 3 months";
  if (place > 0.2) return "in the lower part of its last 3 months";
  return "near its lowest price of the last 3 months";
}

/** One line of the summary: what to do with one holding. */
export function stepLine(step: Step): string {
  return `${step.kind === "buy" ? "Buy" : "Sell"} ${formatMoney(step.amount)} of ${shortName(step.name)}`;
}

/**
 * The purchase drawn as steps down a price line: today's price on the right, each lower
 * price to its left, with how much to buy at each.
 */
export function Ladder({ step }: { step: Step }) {
  const deepest = Math.max(...step.rungs.map((r) => r.below), 0);
  const at = (below: number) => (deepest > 0 ? 100 - (below / deepest) * 84 : 50);
  const last = step.rungs.length - 1;
  return (
    <div
      role="img"
      aria-label={step.rungs
        .map((r, i) =>
          i === 0
            ? `Buy ${formatMoney(r.amount)} now at about ${formatPrice(r.price)}`
            : `Buy ${formatMoney(r.amount)} at ${formatPrice(r.price)} or lower`,
        )
        .join("; ")}
    >
      <div className="relative h-14">
        <span className="absolute inset-x-0 top-1/2 h-px bg-line-strong" />
        {step.rungs.map((rung, i) => {
          const align =
            i === 0 ? "items-end text-right" : i === last ? "items-start" : "items-center";
          const shift = i === 0 ? "-translate-x-full" : i === last ? "" : "-translate-x-1/2";
          return (
            <span
              key={rung.price}
              className={`absolute top-0 flex h-full flex-col justify-between ${align} ${shift}`}
              style={{ left: `${at(rung.below)}%` }}
            >
              <span className="num whitespace-nowrap text-xs text-muted">
                {i === 0 ? "now " : ""}
                {formatPrice(rung.price)}
              </span>
              <span className="num whitespace-nowrap text-sm font-semibold">
                {formatMoney(rung.amount)}
              </span>
            </span>
          );
        })}
        {step.rungs.map((rung, i) => (
          <span
            key={`dot-${rung.price}`}
            className={`absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full ${
              i === 0 ? "bg-accent" : "border-2 border-accent bg-[var(--bg)]"
            }`}
            style={{ left: `${at(rung.below)}%` }}
          />
        ))}
      </div>
      {step.rungs.length > 1 && (
        <div className="mt-1 flex justify-between text-xs text-faint">
          <span>← buy more if it falls</span>
          <span>today</span>
        </div>
      )}
    </div>
  );
}

/** Two marks on one line: the share now and the share the plan asks for. */
function ShareBar({ step }: { step: Step }) {
  const reach = Math.max(step.share_now, step.share_plan, 0.01) * 1.15;
  return (
    <div
      role="img"
      aria-label={`${share(step.share_now)} of your account now; your plan says ${share(step.share_plan)}`}
    >
      <div className="relative h-2 rounded-full bg-line">
        <span
          className="absolute inset-y-0 left-0 rounded-full bg-accent"
          style={{ width: `${(step.share_now / reach) * 100}%` }}
        />
        <span
          className="absolute top-[-3px] h-[14px] w-0.5 bg-ink"
          style={{ left: `${(step.share_plan / reach) * 100}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between text-xs text-muted">
        <span>
          <span className="num text-ink">{share(step.share_now)}</span> now
        </span>
        <span>
          plan <span className="num text-ink">{share(step.share_plan)}</span>
        </span>
      </div>
    </div>
  );
}

/** A dot on a line from the lowest to the highest price of the last three months. */
function PlaceLine({ place }: { place: number }) {
  return (
    <div role="img" aria-label={`The price is ${placeWords(place)}`}>
      <div className="relative h-2 rounded-full bg-line">
        <span
          className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink"
          style={{ left: `${Math.min(Math.max(place, 0.03), 0.97) * 100}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between text-xs text-muted">
        <span>3-month low</span>
        <span>3-month high</span>
      </div>
    </div>
  );
}

function StepCard({ step, by }: { step: Step; by: string }) {
  const buy = step.kind === "buy";
  return (
    <article className="well flex flex-col gap-4 p-4">
      <h3 className="text-base font-semibold tracking-tight">{stepLine(step)}</h3>
      {buy && <Ladder step={step} />}
      <div className="grid grid-cols-1 gap-4 @md:grid-cols-2">
        <div>
          <p className="label mb-2">Share of your account</p>
          <ShareBar step={step} />
        </div>
        {step.place != null && (
          <div>
            <p className="label mb-2">Where the price is</p>
            <PlaceLine place={step.place} />
          </div>
        )}
      </div>
      {buy && step.rungs.length > 1 && (
        <p className="text-xs text-muted">
          Not all bought by {formatDate(by)}? Buy the rest that day.
          {step.weekly_swing != null &&
            ` Steps are ${percent(step.weekly_swing)} apart: a usual week's move.`}
        </p>
      )}
      {step.past && (
        <p className="text-xs text-muted">
          In {step.past.months} past months, buying in steps paid{" "}
          <span className="num text-ink">
            {percent(step.past.average_saving)} {step.past.average_saving < 0 ? "more" : "less"}
          </span>{" "}
          on average than buying all at once, and got a lower price in{" "}
          <span className="num text-ink">{Math.round(step.past.cheaper_share * 100)} of 100</span>{" "}
          months.
        </p>
      )}
      {!buy && (
        <p className="text-xs text-muted">
          Selling this much brings it back to its share of your plan.
        </p>
      )}
    </article>
  );
}

/** What to do with cash the plan does not keep: what to buy, at what prices, and why. */
export function StepsPanel({ steps }: { steps: Steps }) {
  if (!steps.has_plan) {
    return (
      <Message>
        Pick a plan first: how much of your account goes into each thing.{" "}
        <Link to="/portfolio/try" className="font-medium text-ink underline underline-offset-2">
          Choose your shares
        </Link>
      </Message>
    );
  }
  const todo = steps.steps.length > 0;
  return (
    <Panel
      id="steps"
      title="What to do now"
      headline={
        todo
          ? steps.spare > 0
            ? `${formatMoney(steps.spare)} of your cash is spare`
            : "One of your holdings has grown past its share"
          : "Nothing to do right now"
      }
    >
      {!todo && (
        <p className="text-sm text-muted">
          Your account matches your plan. This updates when you add cash or prices move.
        </p>
      )}
      {todo && (
        <div className="grid grid-cols-1 gap-3 @4xl:grid-cols-2">
          {steps.steps.map((step) => (
            <StepCard key={`${step.kind}-${step.symbol}`} step={step} by={steps.by} />
          ))}
        </div>
      )}
      <Caption
        facts={[
          {
            label: "Cash now",
            value: `${formatMoney(steps.cash)}; your plan keeps ${formatMoney(steps.cash_plan)}`,
          },
          { label: "Updates", value: "Each time you look, from your balances and your plan" },
          { label: "You place the trades", value: "RADAR cannot buy or sell anything" },
        ]}
      >
        RADAR cannot tell which way a price goes next. Buying in steps does not get a better price
        on average; it stops you putting everything in at one price that turns out to be the top.
      </Caption>
    </Panel>
  );
}

/** The same thing in one card, for Home. */
export function StepsCard({ steps }: { steps: Steps }) {
  const todo = steps.has_plan && steps.steps.length > 0;
  const first = steps.steps.find((s) => s.kind === "buy");
  return (
    <Link
      to="/portfolio/todo"
      className="glass press block h-full p-4 @xl:p-7"
      aria-label="What to do now"
    >
      <p className="label">What to do now</p>
      <p className="mt-1.5 text-lg font-semibold tracking-tight">
        {!steps.has_plan
          ? "Pick a plan to get started"
          : todo
            ? steps.steps.map(stepLine).join(" · ")
            : "Nothing to do right now"}
      </p>
      {todo && first && (
        <div className="mt-4">
          <Ladder step={first} />
        </div>
      )}
      <p className="mt-3 text-sm text-muted">
        {!steps.has_plan
          ? "Choose how much of your account goes into each thing"
          : todo
            ? "See every price and the reasons"
            : "Your account matches your plan"}
      </p>
    </Link>
  );
}
