import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import type { PortfolioAnalysis } from "../api/client";
import { useMixRisk, useSetTarget, useWhatIf } from "../api/queries";
import { formatMoney } from "../lib/format";
import { Skeleton } from "./Skeleton";
import { Caption, Panel } from "./ui";
import { StackBar, holdingColour, type Part } from "./viz";

const CASH = "USD";
/** The most of the account that anything outside the long-run holdings may take. */
const SMALL_BET_CAP = 1;
const shortName = (name: string) => name.split(" (")[0] ?? name;

/** What each holding is, by symbol: "stocks", "gold", "bitcoin", or nothing. */
export type Kinds = Record<string, string | null | undefined>;

/** Three starting points. Shares of the whole account, in percent; cash is the rest. */
export const STARTS = [
  { key: "careful", label: "Careful", stocks: 25, gold: 20, bitcoin: 7 },
  { key: "middle", label: "Middle", stocks: 37, gold: 20, bitcoin: 15 },
  { key: "bolder", label: "Bolder", stocks: 43, gold: 17, bitcoin: 28 },
] as const;
type Start = (typeof STARTS)[number];

type Shares = Record<string, number>;

/**
 * A starting point turned into shares for the holdings the account really has. Each kind
 * of long-run holding takes its share; where two holdings are the same kind they split
 * it; anything else keeps what it has, up to the cap for a small bet.
 */
export function sharesFor(start: Start, symbols: string[], now: Shares, kinds: Kinds): Shares {
  const count = (kind: string) => symbols.filter((s) => kinds[s] === kind).length;
  return Object.fromEntries(
    symbols.map((s) => {
      const kind = kinds[s];
      if (kind === "stocks" || kind === "gold" || kind === "bitcoin") {
        return [s, Math.round(start[kind] / count(kind))];
      }
      return [s, Math.min(now[s] ?? 0, SMALL_BET_CAP)];
    }),
  );
}

/** One starting point, with how far that mix of these holdings has fallen before. */
function StartButton({
  start,
  shares,
  onPick,
}: {
  start: Start;
  shares: Shares;
  onPick: () => void;
}) {
  const weights = Object.fromEntries(Object.entries(shares).map(([s, v]) => [s, v / 100]));
  const risk = useMixRisk(weights);
  return (
    <button type="button" className="well press p-3 text-left" onClick={onPick}>
      <span className="block text-sm font-semibold">{start.label}</span>
      <span className="mt-0.5 block text-xs text-muted">
        {risk.data ? (
          `fell up to ${Math.abs(risk.data.deepest_fall * 100).toFixed(0)}%`
        ) : risk.isPending ? (
          <Skeleton className="h-3 w-16" />
        ) : (
          "past fall not known"
        )}
      </span>
    </button>
  );
}

export function PlanPanel({ analysis, kinds }: { analysis: PortfolioAnalysis; kinds: Kinds }) {
  const holdings = analysis.positions.filter((p) => p.symbol !== CASH);
  const symbols = holdings.map((p) => p.symbol);
  const now: Shares = Object.fromEntries(
    holdings.map((p) => [p.symbol, Math.round(p.weight * 100)]),
  );
  const saved = analysis.plan?.moves ?? [];
  const [shares, setShares] = useState<Shares>(() =>
    saved.length > 0
      ? Object.fromEntries(
          symbols.map((s) => [
            s,
            Math.round((saved.find((m) => m.symbol === s)?.target_weight ?? 0) * 100),
          ]),
        )
      : now,
  );
  const [touched, setTouched] = useState(false);
  const preview = useWhatIf();
  const save = useSetTarget();
  const invested = symbols.reduce((sum, s) => sum + (shares[s] ?? 0), 0);
  const cash = 100 - invested;
  const weights = Object.fromEntries(symbols.map((s) => [s, (shares[s] ?? 0) / 100]));
  const key = JSON.stringify(weights);

  // Work out the risk of the mix a moment after the last change, not on every pixel.
  const { mutate } = preview;
  useEffect(() => {
    if (cash < 0) return;
    const timer = window.setTimeout(() => mutate({ weights: JSON.parse(key) as Shares }), 350);
    return () => window.clearTimeout(timer);
  }, [key, cash, mutate]);

  const set = (symbol: string, value: number) => {
    const others = invested - (shares[symbol] ?? 0);
    const cap = kinds[symbol] ? 100 : SMALL_BET_CAP;
    setShares({ ...shares, [symbol]: Math.max(0, Math.min(value, cap, 100 - others)) });
    setTouched(true);
  };
  const colour = (symbol: string) => holdingColour(symbol);
  const parts: Part[] = [
    ...holdings.map((p) => ({
      key: p.symbol,
      name: shortName(p.name),
      share: (shares[p.symbol] ?? 0) / 100,
      colour: colour(p.symbol),
    })),
    { key: CASH, name: "Cash", share: Math.max(cash, 0) / 100, colour: "var(--faint)" },
  ];
  const result = preview.data;

  return (
    <Panel id="plan" title="My plan" headline="How much of your account goes into each thing">
      <div>
        <p className="label mb-2">Start from</p>
        <div className="grid grid-cols-3 gap-2 @xl:gap-3">
          {STARTS.map((start) => {
            const picked = sharesFor(start, symbols, now, kinds);
            return (
              <StartButton
                key={start.key}
                start={start}
                shares={picked}
                onPick={() => {
                  setShares(picked);
                  setTouched(true);
                }}
              />
            );
          })}
        </div>
      </div>

      <div>
        <StackBar parts={parts} label="Your plan" />
        <ul className="mt-4 flex flex-col gap-4">
          {holdings.map((p) => (
            <li key={p.symbol}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="flex min-w-0 items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ background: colour(p.symbol) }}
                    aria-hidden="true"
                  />
                  <span className="truncate font-medium">{shortName(p.name)}</span>
                  {!kinds[p.symbol] && (
                    <span className="shrink-0 text-xs text-muted">small bet, 1% at most</span>
                  )}
                </span>
                <span className="num shrink-0">
                  <span className="font-semibold">{shares[p.symbol] ?? 0}%</span>{" "}
                  <span className="text-muted">
                    {formatMoney(((shares[p.symbol] ?? 0) / 100) * analysis.value)}
                  </span>
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={kinds[p.symbol] ? 100 : SMALL_BET_CAP}
                step={1}
                value={shares[p.symbol] ?? 0}
                onChange={(event) => set(p.symbol, Number(event.target.value))}
                aria-label={`${shortName(p.name)} share`}
                className="slider mt-2 w-full"
                style={{ accentColor: colour(p.symbol) }}
              />
              <p className="mt-0.5 text-xs text-faint">Now {now[p.symbol] ?? 0}%</p>
            </li>
          ))}
          <li className="flex items-baseline justify-between gap-3 border-t border-line pt-3 text-sm">
            <span className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-faint" aria-hidden="true" />
              <span className="font-medium">Cash</span>
              <span className="text-xs text-muted">whatever is left</span>
            </span>
            <span className="num">
              <span className="font-semibold">{cash}%</span>{" "}
              <span className="text-muted">{formatMoney((cash / 100) * analysis.value)}</span>
            </span>
          </li>
        </ul>
      </div>

      {result && (
        <div className="grid grid-cols-3 gap-2 @xl:gap-3" aria-live="polite">
          <div className="well p-3">
            <p className="label">A usual day</p>
            <p className="num mt-1 text-lg font-semibold">
              ±{formatMoney(result.daily_volatility * analysis.value)}
            </p>
          </div>
          <div className="well p-3">
            <p className="label">Worst fall so far</p>
            <p className="num mt-1 text-lg font-semibold text-alert">
              −{Math.abs(result.deepest_fall * 100).toFixed(0)}%
            </p>
          </div>
          <div className="well p-3">
            <p className="label">Risk</p>
            <p className="mt-1 text-lg font-semibold capitalize">{result.level ?? "–"}</p>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="btn btn-primary press disabled:opacity-60"
          disabled={save.isPending || cash < 0}
          onClick={() => save.mutate({ weights }, { onSuccess: () => setTouched(false) })}
        >
          {save.isPending ? "Saving…" : "Save as my plan"}
        </button>
        {save.isSuccess && !touched && (
          <Link to="/portfolio/todo" className="text-sm font-medium text-accent">
            Saved. See what to do now →
          </Link>
        )}
        {save.isError && (
          <span className="text-sm text-alert" role="alert">
            That did not save. Please try again.
          </span>
        )}
      </div>

      <Caption
        facts={[
          {
            label: "Worst fall so far",
            value: "The deepest drop this mix would have had in past prices",
          },
          {
            label: "The three starts",
            value: "Their falls are from December 2021 to October 2026",
          },
          { label: "Saving", value: "Changes what RADAR compares you with; nothing is traded" },
        ]}
      >
        A plan with more cash falls less and grows less. Past falls are a guide to how rough it can
        get, not a limit.
      </Caption>
    </Panel>
  );
}
