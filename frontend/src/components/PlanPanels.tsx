import type { PortfolioAnalysis, PortfolioPlan } from "../api/client";
import { useSetTarget } from "../api/queries";
import { formatChange, formatCount, formatMoney, formatShare } from "../lib/format";
import {
  LEVEL_WORDS,
  MIX_NAMES,
  levelNow,
  signalText,
  type LevelName,
  type MixName,
} from "../lib/plan";
import { formatDate } from "../lib/time";
import { MixBuilder } from "./MixBuilder";
import { Caption, Message, Panel } from "./ui";
import { Bars, Legend, Spark, StackBar, holdingColour, type Part } from "./viz";

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

/** Try any mix of your own, then see how far the portfolio is from the one you chose. */
export function LevelsPanel({ analysis }: { analysis: PortfolioAnalysis }) {
  const plan = analysis.plan;
  const name = nameOf(analysis);
  const target = plan?.target;
  const here = levelNow(plan);
  const chosen = target
    ? target.weights
      ? "a mix of your own"
      : `${target.level ? LEVEL_WORDS[target.level] : ""} risk`
    : undefined;

  return (
    <Panel
      id="try"
      title="Try a mix"
      trust={analysis.trust.xray}
      headline={
        chosen
          ? `Your target is ${chosen}; today your mix reads ${here}`
          : `Today your mix reads ${here}. Try another to compare`
      }
    >
      <MixBuilder analysis={analysis} />

      {plan && target && plan.moves.length > 0 && (
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
          <Caption
            facts={[
              { label: "Grey bar", value: "Each holding's share today" },
              { label: "Blue mark", value: "Its share under your target" },
              {
                label: "The amount",
                value: "The gap at today's value, in bold when wider than 5 points",
              },
              {
                label: "Target chosen",
                value: target.set_at ? formatDate(target.set_at) : "On an earlier day",
              },
            ]}
          />
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
  // A split is applied to a risk level; a mix of the user's own already fixes every share.
  const level = plan.target?.weights ? undefined : (plan.target?.level ?? undefined);
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
                disabled={!level || inUse || setTarget.isPending}
                onClick={() => level && setTarget.mutate({ level, split: mix.method as MixName })}
              >
                {inUse ? "In use" : "Use for my target"}
              </button>
            </li>
          );
        })}
      </ul>
      <Legend parts={parts(Object.fromEntries(order.map((s) => [s, 1])), order, name)} />
      {!level && (
        <p className="text-sm text-muted">
          These splits apply to a risk-level target. To use your own numbers, start from one on Try
          a mix.
        </p>
      )}
      <Caption
        facts={[
          {
            label: "Shows",
            value:
              "The same holdings split a different way by each mix, with today's share kept in cash",
          },
          { label: "Cap", value: "No holding above 60%, except in your own split" },
          {
            label: "Window",
            value: `${sample ? formatCount(sample.n_days) : ""} trading days, ${sample ? formatDate(sample.first_day) : ""} to ${sample ? formatDate(sample.last_day) : ""}`,
          },
          {
            label: "Method",
            value:
              "Re-split every 21 trading days at a cost of 0.1%, each time using only the 250 days before",
          },
          { label: "Left out", value: "Holdings with a short price record" },
        ]}
      >
        Growth is what happened then and says nothing about what comes next.
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
      note: "Try a mix and set it as your target",
      level: undefined,
    };
  }
  const flags = plan.signals.filter((s) => s.kind !== "turbulent").length;
  return {
    figure:
      flags === 0 ? "On target" : flags === 1 ? "1 thing has moved" : `${flags} things have moved`,
    note:
      plan.target.weights || !plan.target.level
        ? "Target: a mix of your own"
        : `Target: ${LEVEL_WORDS[plan.target.level]} risk`,
    level: plan.target.level ?? undefined,
  };
}
