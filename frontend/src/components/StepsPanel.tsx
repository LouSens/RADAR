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

function Rungs({ step, by }: { step: Step; by: string }) {
  return (
    <ol className="mt-3">
      {step.rungs.map((rung, i) => (
        <li
          key={rung.price}
          className="flex items-baseline justify-between gap-3 border-t border-line py-2.5 first:border-t-0"
        >
          <span className="text-sm">
            <span className="font-medium">Buy {formatMoney(rung.amount)}</span>{" "}
            <span className="text-muted">
              {i === 0
                ? "now"
                : `if the price falls ${percent(rung.below)}, to ${formatPrice(rung.price)} or lower`}
            </span>
          </span>
          {i === 0 && <span className="num shrink-0 text-sm">about {formatPrice(rung.price)}</span>}
        </li>
      ))}
      {step.rungs.length > 1 && (
        <li className="border-t border-line py-2.5 text-sm text-muted">
          Whatever is not bought by {formatDate(by)}: buy it that day.
        </li>
      )}
    </ol>
  );
}

function Why({ step }: { step: Step }) {
  const facts = [
    {
      label: "Your plan",
      value: `It is ${share(step.share_now)} of your account now; your plan says ${share(step.share_plan)}`,
    },
  ];
  if (step.place != null && step.below_high != null) {
    facts.push({
      label: "Where the price is",
      value: `${placeWords(step.place).replace(/^./, (c) => c.toUpperCase())}${
        step.below_high < -0.005 ? `, ${percent(step.below_high)} below the highest` : ""
      }`,
    });
  }
  if (step.weekly_swing != null && step.rungs.length > 1) {
    facts.push({
      label: "Why these prices",
      value: `It usually moves about ${percent(step.weekly_swing)} in a week; each step is that far apart`,
    });
  }
  if (step.past) {
    const dearer = step.past.average_saving < 0;
    facts.push({
      label: "What buying in steps did before",
      value: `Over ${step.past.months} past months it paid ${percent(step.past.average_saving)} ${
        dearer ? "more" : "less"
      } on average than buying all at once, and got a lower price in ${Math.round(
        step.past.cheaper_share * 100,
      )} months out of 100`,
    });
  }
  return (
    <div className="mt-4 border-t border-line pt-3">
      <p className="label">Why</p>
      <dl className="facts mt-2">
        {facts.map((fact) => (
          <div key={fact.label}>
            <dt className="label">{fact.label}</dt>
            <dd>{fact.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function StepCard({ step, by }: { step: Step; by: string }) {
  const buy = step.kind === "buy";
  return (
    <article className="well p-4">
      <h3 className="text-base font-semibold tracking-tight">{stepLine(step)}</h3>
      {!buy && (
        <p className="mt-1 text-sm text-muted">
          It has grown to {share(step.share_now)} of your account; your plan says{" "}
          {share(step.share_plan)}. Selling this much brings it back.
        </p>
      )}
      {buy && <Rungs step={step} by={by} />}
      {buy && <Why step={step} />}
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
            ? `You have ${formatMoney(steps.spare)} more cash than your plan keeps`
            : "One of your holdings has grown past its share"
          : "Nothing to do right now"
      }
    >
      {!todo && (
        <p className="text-sm text-muted">
          Your account matches your plan closely enough. This updates when you add cash or prices
          move.
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
          { label: "Worked out", value: "From your balances and your plan, each time you look" },
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
  return (
    <Link
      to="/portfolio/todo"
      className="glass press block p-4 @xl:p-7"
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
      <p className="mt-1 text-sm text-muted">
        {!steps.has_plan
          ? "Choose how much of your account goes into each thing"
          : todo
            ? "See the prices and the reasons"
            : "Your account matches your plan"}
      </p>
    </Link>
  );
}
