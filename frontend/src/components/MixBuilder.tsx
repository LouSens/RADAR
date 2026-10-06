import { useState } from "react";

import type { PortfolioAnalysis, WhatIf } from "../api/client";
import { usePortfolio, useSetTarget, useWhatIf } from "../api/queries";
import { formatMoney, formatShare } from "../lib/format";
import { MIX_NAMES, dayLimit, levelNow, presets, type MixName, type Preset } from "../lib/plan";
import { TickerBox } from "./TickerBox";
import { Caption } from "./ui";
import { Bars, StackBar, holdingColour, levelColour } from "./viz";

const CASH = "USD";

interface Row {
  symbol: string;
  percent: number;
}

const field =
  "h-9 rounded-xl border border-line bg-white/[0.04] px-2 text-sm text-ink outline-none transition-colors focus:border-line-strong";

const round = (value: number) => Math.round(value * 10) / 10;

function rowsFrom(shares: Record<string, number>, order: string[]): Row[] {
  const seen = [...order, ...Object.keys(shares).filter((s) => !order.includes(s))];
  return seen
    .filter((symbol) => symbol !== CASH && (shares[symbol] ?? 0) > 0.0005)
    .map((symbol) => ({ symbol, percent: round((shares[symbol] ?? 0) * 100) }));
}

/**
 * Try any mix: give each holding a share of your money and see how much the result
 * would move. Nothing is saved or traded by trying.
 */
export function MixBuilder({ analysis }: { analysis: PortfolioAnalysis }) {
  const supported = usePortfolio().data?.supported ?? [];
  const tryMix = useWhatIf();
  const setTarget = useSetTarget();
  const order = analysis.positions.map((p) => p.symbol);
  const current = Object.fromEntries(analysis.positions.map((p) => [p.symbol, p.weight]));
  const [rows, setRows] = useState<Row[]>(() => rowsFrom(current, order));
  // Names of assets found by ticker, until the list of known assets has caught up.
  const [looked, setLooked] = useState<Record<string, string>>({});

  const name = (symbol: string) =>
    symbol === CASH
      ? "Cash"
      : ((
          analysis.positions.find((p) => p.symbol === symbol)?.name ??
          supported.find((a) => a.symbol === symbol)?.name ??
          looked[symbol] ??
          symbol
        ).split(" (")[0] ?? symbol);

  const invested = rows.reduce((sum, row) => sum + row.percent, 0);
  const cash = round(100 - invested);
  const over = invested > 100.05;
  const empty = rows.every((row) => row.percent <= 0);
  const weights = Object.fromEntries(
    rows.filter((r) => r.percent > 0).map((r) => [r.symbol, r.percent / 100]),
  );
  const result: WhatIf | undefined = tryMix.data;
  const options = supported.filter(
    (a) => a.symbol !== CASH && !rows.some((r) => r.symbol === a.symbol),
  );

  function change(symbol: string, percent: number) {
    const value = Number.isFinite(percent) ? Math.min(Math.max(percent, 0), 100) : 0;
    setRows((before) => before.map((r) => (r.symbol === symbol ? { ...r, percent: value } : r)));
  }

  function start(preset: Preset) {
    const next = rowsFrom(preset.shares, order);
    setRows(next);
    tryMix.mutate({
      weights: Object.fromEntries(next.map((r) => [r.symbol, r.percent / 100])),
    });
  }

  const now = {
    ratio: analysis.risk_level?.ratio,
    day: analysis.covered_value * analysis.xray.daily_volatility,
    limit: dayLimit(analysis),
    fall: analysis.xray.deepest_fall.depth,
  };
  const pair = (
    key: string,
    before: number | undefined | null,
    after: number | undefined | null,
  ) => [
    ...(before != null
      ? [{ key: `${key}-now`, name: "Now", value: before, colour: "var(--muted)" }]
      : []),
    ...(after != null
      ? [{ key: `${key}-mix`, name: "This mix", value: after, colour: "var(--accent)" }]
      : []),
  ];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="label mb-2">Start from</p>
        <div className="flex flex-wrap gap-2">
          {presets(analysis).map((preset) => (
            <button
              key={preset.key}
              type="button"
              className="rounded-full border border-line px-3 py-1.5 text-[13px] font-medium text-muted transition-colors hover:border-line-strong hover:text-ink"
              onClick={() => start(preset)}
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>

      <ul className="flex flex-col gap-3">
        {rows.map((row, i) => (
          <li
            key={row.symbol}
            className="grid grid-cols-[minmax(0,1fr)_4.5rem_auto] items-center gap-x-3 gap-y-1 @xl:grid-cols-[9rem_minmax(0,1fr)_4.5rem_5.5rem_auto]"
          >
            <span className="flex min-w-0 items-center gap-2 text-sm">
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ background: holdingColour(row.symbol, i) }}
                aria-hidden="true"
              />
              <span className="truncate">{name(row.symbol)}</span>
            </span>
            <input
              type="range"
              min={0}
              max={100}
              step={0.5}
              value={row.percent}
              aria-label={`${name(row.symbol)} share, slider`}
              onChange={(event) => change(row.symbol, Number(event.target.value))}
              className="col-span-3 w-full accent-[var(--accent)] @xl:col-span-1"
              style={{ gridRow: undefined }}
            />
            <span className="flex items-center gap-1">
              <input
                type="number"
                min={0}
                max={100}
                step={0.5}
                value={row.percent}
                aria-label={`${name(row.symbol)} share, percent`}
                onChange={(event) => change(row.symbol, Number(event.target.value))}
                className={`${field} num w-full text-right`}
              />
              <span className="text-sm text-muted">%</span>
            </span>
            <span className="num hidden text-right text-sm text-muted @xl:block">
              {formatMoney((row.percent / 100) * analysis.value)}
            </span>
            <button
              type="button"
              aria-label={`Remove ${name(row.symbol)}`}
              onClick={() => setRows((before) => before.filter((r) => r.symbol !== row.symbol))}
              className="grid h-9 w-9 place-items-center rounded-xl text-muted transition-colors hover:bg-white/8 hover:text-ink"
            >
              ×
            </button>
          </li>
        ))}
        <li className="flex items-center justify-between gap-3 border-t border-line pt-3 text-sm">
          <span className="flex items-center gap-2">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ background: holdingColour(CASH, 0) }}
              aria-hidden="true"
            />
            Cash, whatever is left
          </span>
          <span className={`num font-medium ${over ? "text-alert" : ""}`}>
            {over
              ? `${round(invested - 100)}% too much`
              : `${cash}% · ${formatMoney((cash / 100) * analysis.value)}`}
          </span>
        </li>
      </ul>

      {options.length > 0 && (
        <div>
          <p className="label mb-2">Add another asset</p>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Add another asset">
            {options.map((asset) => (
              <button
                key={asset.symbol}
                type="button"
                aria-label={`Add ${name(asset.symbol)}`}
                onClick={() =>
                  setRows((before) => [...before, { symbol: asset.symbol, percent: 0 }])
                }
                className="inline-flex items-center gap-1.5 rounded-full border border-dashed border-line-strong px-3 py-1.5 text-[13px] font-medium text-muted transition-colors hover:border-solid hover:bg-white/5 hover:text-ink"
              >
                <span aria-hidden="true" className="text-base leading-none">
                  +
                </span>
                {name(asset.symbol)}
              </button>
            ))}
          </div>
        </div>
      )}

      <TickerBox
        onFound={(asset) => {
          setLooked((before) => ({ ...before, [asset.symbol]: asset.name }));
          setRows((before) =>
            before.some((r) => r.symbol === asset.symbol)
              ? before
              : [...before, { symbol: asset.symbol, percent: 0 }],
          );
        }}
      />

      <div className="flex flex-wrap items-center gap-2.5">
        <button
          type="button"
          className="btn btn-primary ml-auto disabled:opacity-50"
          disabled={over || empty || tryMix.isPending}
          onClick={() => tryMix.mutate({ weights })}
        >
          {tryMix.isPending ? "Working it out…" : "Work out the risk"}
        </button>
      </div>
      {tryMix.isError && <p className="text-sm text-alert">{tryMix.error.message}</p>}

      {result && (
        <div className="flex flex-col gap-5 border-t border-line pt-5" aria-live="polite">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <h3 className="text-sm font-semibold tracking-tight">This mix</h3>
            {result.ratio != null && result.level && (
              <p className="num text-sm">
                <span
                  className="font-semibold capitalize"
                  style={{ color: levelColour(result.level) }}
                >
                  {result.level}
                </span>{" "}
                <span className="text-muted">
                  · {result.ratio.toFixed(2)}× the daily movement of US stocks
                </span>
              </p>
            )}
          </div>
          <StackBar
            label="Share of the risk in this mix"
            parts={Object.entries(result.risk_shares as Record<string, number>)
              .filter(([, share]) => share > 0.0005)
              .map(([symbol, share], i) => ({
                key: symbol,
                name: name(symbol),
                share,
                colour: holdingColour(symbol, i),
              }))}
          />
          <div className="grid grid-cols-1 gap-x-10 gap-y-5 @3xl:grid-cols-2">
            <div>
              <p className="label mb-2">Movement against US stocks</p>
              <Bars
                format={(v) => `${v.toFixed(2)}×`}
                rows={pair("ratio", now.ratio, result.ratio)}
              />
            </div>
            <div>
              <p className="label mb-2">Typical day</p>
              <Bars
                format={(v) => `±${formatMoney(v)}`}
                rows={pair("day", now.day, result.value * result.daily_volatility)}
              />
            </div>
            <div>
              <p className="label mb-2">Loss on about 1 day in 20</p>
              <Bars
                format={formatMoney}
                rows={pair(
                  "limit",
                  now.limit === undefined ? undefined : analysis.covered_value * now.limit,
                  result.limit_95 == null ? undefined : result.value * result.limit_95,
                )}
              />
            </div>
            <div>
              <p className="label mb-2">Deepest fall on record</p>
              <Bars
                format={(v) => formatShare(v, 1)}
                rows={pair("fall", now.fall, result.deepest_fall)}
              />
            </div>
          </div>
          {result.limit_99 != null && (
            <p className="num text-sm text-muted">
              On about 1 day in 100 the loss would pass{" "}
              <span className="text-ink">{formatMoney(result.value * result.limit_99)}</span>.
            </p>
          )}
          {[...result.young, ...result.unmeasured].length > 0 && (
            <p className="text-sm text-muted">
              {result.young.map(
                (y) => `${y.name} is estimated from only ${y.days} days of prices. `,
              )}
              {result.unmeasured.map(
                (u) => `${u.name} has too few days of prices and is not in these figures. `,
              )}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              className="btn btn-ghost disabled:opacity-50"
              disabled={setTarget.isPending}
              onClick={() =>
                setTarget.mutate({ weights: result.weights as Record<string, number> })
              }
            >
              Set this mix as my target
            </button>
            {setTarget.isSuccess && (
              <span className="text-sm text-calm">Saved as your target.</span>
            )}
            {setTarget.isError && (
              <span className="text-sm text-alert">{setTarget.error.message}</span>
            )}
          </div>
        </div>
      )}

      <Caption>
        Give each holding a share of your {formatMoney(analysis.value)} and the rest is held as
        cash. The figures are worked out the same way as on the other tabs, from the prices stored
        for each holding, so &quot;Now&quot; and &quot;This mix&quot; can be compared directly. Your
        mix reads {levelNow(analysis.plan)} today. Low, moderate, and high are this app&apos;s own
        bands (under half the daily movement of US stocks, up to the same, up to double) and are
        here only as starting points, as are the other splits (
        {(["equal", "min_variance", "equal_risk", "hierarchical"] as MixName[])
          .map((m) => MIX_NAMES[m].toLowerCase())
          .join(", ")}
        ). Trying a mix saves nothing and changes nothing at Binance; neither does setting a target,
        which only decides what your portfolio is compared with.
      </Caption>
    </div>
  );
}
