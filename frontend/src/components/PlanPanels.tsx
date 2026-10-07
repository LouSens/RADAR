import type { PortfolioAnalysis, PortfolioPlan } from "../api/client";
import { formatMoney, formatShare } from "../lib/format";
import { LEVEL_WORDS, levelNow, signalText, type LevelName } from "../lib/plan";
import { formatDate } from "../lib/time";
import { MixBuilder } from "./MixBuilder";
import { Caption, Panel } from "./ui";

const CASH = "USD";

function nameOf(analysis: PortfolioAnalysis) {
  return (symbol: string) =>
    symbol === CASH
      ? "Cash"
      : ((analysis.positions.find((p) => p.symbol === symbol)?.name ?? symbol).split(" (")[0] ??
        symbol);
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
