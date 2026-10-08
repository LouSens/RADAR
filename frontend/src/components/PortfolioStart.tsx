import { CardSkeleton } from "./Skeleton";
import { Link } from "react-router-dom";

import type { AccountRecord, Portfolio, PortfolioAnalysis, Steps } from "../api/client";
import { formatMoney } from "../lib/format";
import { Ladder, stepLine } from "./StepsPanel";
import { Legend, StackBar, holdingColour, type Part } from "./viz";

const CASH = "USD";
const shortName = (name: string) => name.split(" (")[0] ?? name;
const signed = (value: number) => `${value >= 0 ? "+" : "−"}${formatMoney(Math.abs(value))}`;

function Stat({
  label,
  figure,
  note,
  to,
  tone,
  wide = false,
}: {
  label: string;
  figure: string;
  note: string;
  to: string;
  tone?: string;
  wide?: boolean;
}) {
  return (
    <Link
      to={to}
      className={`tile press flex min-w-0 flex-col ${wide ? "col-span-2 @2xl:col-span-1" : ""}`}
      aria-label={label}
    >
      <span className="label">{label}</span>
      <span className={`num mt-1.5 text-[1.25rem] font-semibold tracking-tight ${tone ?? ""}`}>
        {figure}
      </span>
      <span className="mt-0.5 text-xs text-muted">{note}</span>
    </Link>
  );
}

/** The mix as it is now beside the mix the plan asks for, as two bars. */
export function PlanBars({ analysis }: { analysis: PortfolioAnalysis }) {
  const moves = analysis.plan?.moves ?? [];
  const planned = (symbol: string) => moves.find((m) => m.symbol === symbol)?.target_weight;
  const others = analysis.positions.filter((p) => p.symbol !== CASH);
  const colour = (symbol: string) =>
    symbol === CASH
      ? "var(--faint)"
      : holdingColour(
          symbol,
          others.findIndex((p) => p.symbol === symbol),
        );
  const now: Part[] = analysis.positions.map((p) => ({
    key: p.symbol,
    name: shortName(p.name),
    share: p.weight,
    colour: colour(p.symbol),
  }));
  if (moves.length === 0) {
    return (
      <div>
        <StackBar parts={now} label="Your account now" />
        <Legend parts={now} />
        <p className="mt-3 text-sm text-muted">
          You have no plan yet.{" "}
          <Link to="/portfolio/try" className="font-medium text-ink underline underline-offset-2">
            Choose your shares
          </Link>
        </p>
      </div>
    );
  }
  const invested = others.reduce((sum, p) => sum + (planned(p.symbol) ?? 0), 0);
  const plan: Part[] = analysis.positions.map((p) => ({
    key: p.symbol,
    name: shortName(p.name),
    share: p.symbol === CASH ? Math.max(1 - invested, 0) : (planned(p.symbol) ?? 0),
    colour: colour(p.symbol),
  }));
  return (
    <div className="flex flex-col gap-3">
      <div>
        <p className="label mb-1.5">Now</p>
        <StackBar parts={now} label="Your account now" />
      </div>
      <div>
        <p className="label mb-1.5">Your plan</p>
        <StackBar parts={plan} label="Your plan" />
      </div>
      <ul className="mt-1 grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm @xl:grid-cols-3">
        {now.map((part, i) => (
          <li key={part.key} className="flex items-center gap-2">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ background: part.colour }}
              aria-hidden="true"
            />
            <span className="min-w-0 truncate">{part.name}</span>
            <span className="num ml-auto shrink-0 text-muted">
              {Math.round(part.share * 100)}% → {Math.round((plan[i]?.share ?? 0) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The first thing on Portfolio: where you stand, your plan, and the one thing to do. */
export function PortfolioStart({
  portfolio,
  analysis,
  record,
  steps,
}: {
  portfolio: Portfolio;
  analysis: PortfolioAnalysis;
  record: AccountRecord | null | undefined;
  steps: Steps | null | undefined;
}) {
  const earn = portfolio.wallets.find((w) => w.yearly_rate != null && w.earning != null);
  const total = record ? record.realised + record.unrealised : undefined;
  const level = analysis.risk_level;
  const first = steps?.steps.find((s) => s.kind === "buy");
  return (
    <>
      <div className="grid grid-cols-2 gap-2 @2xl:grid-cols-3 @xl:gap-4">
        {total !== undefined && (
          <Stat
            label="All your trades"
            figure={signed(total)}
            note="every coin, all time"
            to="/portfolio/record"
            tone={total < 0 ? "text-alert" : "text-calm"}
            wide
          />
        )}
        {earn?.yearly_rate != null && earn.earning != null && (
          <Stat
            label="Cash in Earn"
            figure={`${(earn.yearly_rate * 100).toFixed(1)}% a year`}
            note={
              earn.bonus_rate != null && earn.bonus_up_to != null
                ? `about ${formatMoney((earn.earning * earn.yearly_rate) / 12)} a month, with a ${(earn.bonus_rate * 100).toFixed(0)}% bonus on the first ${formatMoney(earn.bonus_up_to)} that Binance can change`
                : `about ${formatMoney((earn.earning * earn.yearly_rate) / 12)} a month on ${formatMoney(earn.earning)}`
            }
            to="/portfolio/holdings"
          />
        )}
        {level && (
          <Stat
            label="Risk"
            figure={level.label.replace(/^./, (c) => c.toUpperCase())}
            note={`about ${formatMoney(analysis.xray.daily_volatility * analysis.covered_value)} up or down on a usual day`}
            to="/portfolio/risk"
          />
        )}
      </div>

      <section className="glass p-4 @xl:p-7" aria-labelledby="plan-title">
        <div className="flex items-baseline justify-between gap-3">
          <h2 id="plan-title" className="text-base font-semibold tracking-tight">
            Your account against your plan
          </h2>
          <Link to="/portfolio/try" className="press text-sm font-medium text-muted hover:text-ink">
            Change plan
          </Link>
        </div>
        <div className="mt-4">
          <PlanBars analysis={analysis} />
        </div>
      </section>

      {/* Still being worked out: hold its place, so the card does not jump in later. */}
      {steps === undefined && <CardSkeleton lines={2} />}
      {steps?.has_plan && (
        <Link
          to="/portfolio/todo"
          className="glass press block p-4 @xl:p-7"
          aria-label="What to do now"
        >
          <p className="label">What to do now</p>
          <p className="mt-1.5 text-lg font-semibold tracking-tight">
            {steps.steps.length > 0
              ? steps.steps.map(stepLine).join(" · ")
              : "Nothing to do right now"}
          </p>
          {first && (
            <div className="mt-4">
              <Ladder step={first} />
            </div>
          )}
          <p className="mt-3 text-sm text-muted">
            {steps.steps.length > 0
              ? "See every price and the reasons"
              : "Your account matches your plan"}
          </p>
        </Link>
      )}
    </>
  );
}
