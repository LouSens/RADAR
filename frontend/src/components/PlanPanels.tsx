import type { PortfolioAnalysis, PortfolioPlan } from "../api/client";
import { useSetTarget } from "../api/queries";
import { formatChange, formatCount, formatMoney, formatShare } from "../lib/format";
import {
  LEVEL_WORDS,
  MIX_NAMES,
  dayLimit,
  levelMix,
  levelNow,
  signalText,
  type LevelName,
  type MixName,
} from "../lib/plan";
import { formatDate } from "../lib/time";
import { Caption, Message, Panel } from "./ui";
import { Bars, Legend, Spark, StackBar, holdingColour, levelColour, type Part } from "./viz";

const CASH = "USD";

function nameOf(analysis: PortfolioAnalysis) {
  return (symbol: string) =>
    symbol === CASH
      ? "Cash"
      : ((analysis.positions.find((p) => p.symbol === symbol)?.name ?? symbol).split(" (")[0] ??
        symbol);
}

function parts(
  shares: Record<string, number>,
  order: string[],
  name: (symbol: string) => string,
): Part[] {
  return order
    .filter((symbol) => (shares[symbol] ?? 0) > 0.0005)
    .map((symbol, i) => ({
      key: symbol,
      name: name(symbol),
      share: shares[symbol] ?? 0,
      colour: holdingColour(symbol, i),
    }));
}

/** What a low, moderate, and high level would each look like with these holdings. */
export function LevelsPanel({ analysis }: { analysis: PortfolioAnalysis }) {
  const plan = analysis.plan;
  const setTarget = useSetTarget();
  if (!plan)
    return <Message>There is not enough history to place this mix on the scale yet.</Message>;
  const name = nameOf(analysis);
  const order = [...analysis.xray.symbols, CASH];
  const here = levelNow(plan);
  const target = plan.target;
  const split = target?.split ?? "current";
  const limit = dayLimit(analysis);

  return (
    <Panel
      id="levels"
      title="Risk levels"
      trust={analysis.trust.xray}
      headline={
        target
          ? `Your target is ${LEVEL_WORDS[target.level]}; today the mix reads ${here}`
          : `Today the mix reads ${here}. No target chosen`
      }
    >
      <div className="grid grid-cols-1 gap-4 @3xl:grid-cols-3">
        {plan.levels.map((level) => {
          const mix = levelMix(analysis, plan, level);
          const chosen = target?.level === level.level;
          const scale = plan.ratio > 0 ? level.ratio / plan.ratio : 0;
          return (
            <section
              key={level.level}
              aria-label={`${LEVEL_WORDS[level.level]} risk`}
              className="well flex flex-col gap-3 p-4"
              style={chosen ? { borderColor: levelColour(level.level) } : undefined}
            >
              <div className="flex items-baseline justify-between gap-2">
                <h3
                  className="text-lg font-semibold capitalize tracking-tight"
                  style={{ color: levelColour(level.level) }}
                >
                  {LEVEL_WORDS[level.level]}
                </h3>
                <span className="text-xs text-muted">
                  {chosen ? "Your target" : here === level.level ? "You are here" : ""}
                </span>
              </div>
              <p className="num text-sm text-muted">
                {level.ratio.toFixed(2)}× the daily movement of US stocks
              </p>
              <StackBar
                parts={parts(mix, order, name)}
                label={`${LEVEL_WORDS[level.level]} risk mix`}
              />
              <dl className="num grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                <dt className="text-muted">Cash</dt>
                <dd className="text-right font-medium">
                  {formatShare(level.cash_share, 0)} ·{" "}
                  {formatMoney(level.cash_share * analysis.covered_value)}
                </dd>
                <dt className="text-muted">Typical day</dt>
                <dd className="text-right font-medium">
                  ±{formatMoney(analysis.covered_value * analysis.xray.daily_volatility * scale)}
                </dd>
                {limit !== undefined && (
                  <>
                    <dt className="text-muted">Loss on 1 day in 20</dt>
                    <dd className="text-right font-medium">
                      {formatMoney(analysis.covered_value * limit * scale)}
                    </dd>
                  </>
                )}
              </dl>
              {!level.reachable && (
                <p className="text-xs leading-relaxed text-alert">
                  These holdings swing {plan.invested_ratio.toFixed(2)}× even with no cash, so this
                  level is out of reach without borrowing.
                </p>
              )}
              <button
                type="button"
                className={`btn mt-auto ${chosen ? "btn-ghost" : "btn-primary"} disabled:opacity-50`}
                disabled={setTarget.isPending}
                onClick={() => setTarget.mutate({ level: chosen ? null : level.level, split })}
              >
                {chosen ? "Clear target" : "Set as my target"}
              </button>
            </section>
          );
        })}
      </div>
      <Legend parts={parts(Object.fromEntries(order.map((s) => [s, 1])), order, name)} />
      {setTarget.isError && <p className="text-sm text-alert">{setTarget.error.message}</p>}
      <Caption>
        Each card keeps your holdings in the proportions of the split in use (
        {MIX_NAMES[split].toLowerCase()}) and changes only the share kept in cash, which is what
        sets how much the whole mix moves. The levels are this app&apos;s own convention: low is
        under half the daily movement of US stocks, moderate up to the same, high up to double.
        Money figures scale today&apos;s typical day and loss limit to each level. Setting a target
        changes nothing at Binance; it only sets what your portfolio is compared with.
      </Caption>

      {target && plan.target_plan && (
        <div className="border-t border-line pt-5">
          <h3 className="text-sm font-semibold tracking-tight">Distance from your target</h3>
          {plan.signals.length === 0 ? (
            <p className="mt-2 text-sm text-calm">Within your target on every measure.</p>
          ) : (
            <ul className="mt-2 flex flex-col gap-1.5 text-sm">
              {plan.signals.map((signal) => (
                <li key={signal.kind} className="flex gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-alert" />
                  <span>{signalText(signal, name)}</span>
                </li>
              ))}
            </ul>
          )}
          <ul className="mt-4">
            {plan.moves.map((move) => (
              <li
                key={move.symbol}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 border-t border-line py-3 first:border-t-0"
              >
                <div className="min-w-0">
                  <p className="flex items-baseline justify-between gap-3 text-sm">
                    <span className={move.drifted ? "font-medium" : ""}>{name(move.symbol)}</span>
                    <span className="num text-muted">
                      {formatShare(move.current_weight, 0)} now · target{" "}
                      {formatShare(move.target_weight, 0)}
                    </span>
                  </p>
                  <span className="relative mt-1.5 block h-1.5 rounded-full bg-white/8">
                    <span
                      className="absolute inset-y-0 left-0 rounded-full bg-white/40"
                      style={{ width: `${Math.min(move.current_weight, 1) * 100}%` }}
                    />
                    <span
                      className="absolute -inset-y-1 w-0.5 bg-accent"
                      style={{ left: `${Math.min(move.target_weight, 1) * 100}%` }}
                    />
                  </span>
                </div>
                <span
                  className={`num w-20 text-right text-sm ${move.drifted ? "font-semibold text-ink" : "text-muted"}`}
                >
                  {Math.abs(move.change_value) < 0.005
                    ? "–"
                    : `${move.change_value > 0 ? "+" : "−"}${formatMoney(Math.abs(move.change_value))}`}
                </span>
              </li>
            ))}
          </ul>
          <Caption>
            The grey bar is each holding&apos;s share of your money today and the blue mark its
            share under your target. The amount on the right is the size of the gap at today&apos;s
            value; the amounts cancel out. A gap is in bold when it is wider than 5 percentage
            points. Chosen on {target.set_at ? formatDate(target.set_at) : "an earlier day"}.
          </Caption>
        </div>
      )}
    </Panel>
  );
}

/** Five ways to split the same holdings, run through the stored history. */
export function MixesPanel({ analysis }: { analysis: PortfolioAnalysis }) {
  const plan = analysis.plan;
  const setTarget = useSetTarget();
  if (!plan || plan.mixes.length === 0) {
    return <Message>Comparing mixes needs at least two holdings with a long price record.</Message>;
  }
  const name = nameOf(analysis);
  const steadiest = plan.mixes.reduce((a, b) => (b.daily_volatility < a.daily_volatility ? b : a));
  const sample = plan.mixes[0];
  const order = Object.keys(sample?.weights_now ?? {});
  const colour = (method: string) =>
    method === (plan.target?.split ?? "current") ? "var(--accent)" : "var(--muted)";
  return (
    <Panel
      id="mixes"
      title="Compare mixes"
      trust={plan.trust}
      headline={`${MIX_NAMES[steadiest.method as MixName]} moved least: ±${formatShare(steadiest.daily_volatility)} a day`}
    >
      <div className="grid grid-cols-1 gap-x-10 gap-y-6 @3xl:grid-cols-2">
        <div>
          <h3 className="label mb-3">Daily movement</h3>
          <Bars
            format={(v) => `±${formatShare(v)}`}
            rows={plan.mixes.map((mix) => ({
              key: mix.method,
              name: MIX_NAMES[mix.method as MixName],
              value: mix.daily_volatility,
              colour: colour(mix.method),
            }))}
          />
        </div>
        <div>
          <h3 className="label mb-3">Deepest fall</h3>
          <Bars
            format={(v) => formatShare(v, 1)}
            rows={plan.mixes.map((mix) => ({
              key: mix.method,
              name: MIX_NAMES[mix.method as MixName],
              value: mix.deepest_fall,
              colour:
                mix.method === (plan.target?.split ?? "current") ? "var(--accent)" : "var(--alert)",
            }))}
          />
        </div>
      </div>

      <ul className="border-t border-line">
        {plan.mixes.map((mix) => {
          const inUse = mix.method === (plan.target?.split ?? "current");
          return (
            <li
              key={mix.method}
              className="grid grid-cols-1 gap-x-8 gap-y-3 border-b border-line py-4 last:border-b-0 @3xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_auto] @3xl:items-center"
            >
              <div>
                <p className="flex items-baseline justify-between gap-3">
                  <span className="font-medium">{MIX_NAMES[mix.method as MixName]}</span>
                  <span className="num text-xs text-muted">
                    {formatChange(mix.total_return)} over the period
                  </span>
                </p>
                <div className="mt-2">
                  <StackBar
                    parts={parts(mix.weights_now as Record<string, number>, order, name)}
                    label={`${MIX_NAMES[mix.method as MixName]} split`}
                  />
                </div>
                <p className="num mt-1.5 text-xs text-faint">
                  {order
                    .map(
                      (s) =>
                        `${name(s)} ${formatShare((mix.weights_now as Record<string, number>)[s] ?? 0, 0)}`,
                    )
                    .join(" · ")}
                </p>
              </div>
              <div>
                <Spark
                  values={mix.path}
                  colour={inUse ? "var(--accent)" : "var(--muted)"}
                  label={`Value of ${MIX_NAMES[mix.method as MixName]} over time`}
                />
                <p className="num mt-1 text-xs text-faint">
                  {formatShare(mix.turnover, 1)} of the mix traded each month
                </p>
              </div>
              <button
                type="button"
                className="btn btn-ghost disabled:opacity-50"
                disabled={!plan.target || inUse || setTarget.isPending}
                onClick={() =>
                  plan.target &&
                  setTarget.mutate({ level: plan.target.level, split: mix.method as MixName })
                }
              >
                {inUse ? "In use" : "Use for my target"}
              </button>
            </li>
          );
        })}
      </ul>
      <Legend parts={parts(Object.fromEntries(order.map((s) => [s, 1])), order, name)} />
      {!plan.target && (
        <p className="text-sm text-muted">Choose a risk level first to use one of these splits.</p>
      )}
      <Caption>
        Each mix splits the same holdings a different way and keeps today&apos;s share in cash.
        &quot;As it is now&quot; holds your current proportions; &quot;equal shares&quot; gives each
        holding the same; &quot;smallest movement&quot; is the split that moved least; &quot;equal
        risk each&quot; makes every holding carry the same share of the risk; &quot;grouped by
        behaviour&quot; shares risk between groups of holdings that move alike. No holding goes
        above 60% except in your own split. Run over {sample ? formatCount(sample.n_days) : ""}{" "}
        trading days from {sample ? formatDate(sample.first_day) : ""} to{" "}
        {sample ? formatDate(sample.last_day) : ""}, rebalanced every 21 sessions with a trading
        cost of 0.1%, each decision using only the 250 sessions before it. Holdings with a short
        price record are left out. Growth is what happened over that period and says nothing about
        what comes next.
      </Caption>
    </Panel>
  );
}

/** For the summary: where the mix stands against the chosen target, in one tile's worth. */
export function targetSummary(plan: PortfolioPlan | null | undefined): {
  figure: string;
  note: string;
  level: LevelName | undefined;
} {
  if (!plan?.target) {
    return {
      figure: "No target yet",
      note: "Choose a risk level to compare against",
      level: undefined,
    };
  }
  const flags = plan.signals.filter((s) => s.kind !== "turbulent").length;
  return {
    figure:
      flags === 0 ? "On target" : flags === 1 ? "1 thing has moved" : `${flags} things have moved`,
    note: `Target: ${LEVEL_WORDS[plan.target.level]} risk`,
    level: plan.target.level,
  };
}
