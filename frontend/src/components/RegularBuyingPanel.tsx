import { useEffect, useRef, useState } from "react";

import type { Portfolio, PortfolioAnalysis, RegularBuying } from "../api/client";
import { useRegularBuying } from "../api/queries";
import { formatChange, formatCount, formatMoney, formatShare } from "../lib/format";
import { formatDate } from "../lib/time";
import { TickerBox } from "./TickerBox";
import { Caption, Panel, Segmented } from "./ui";
import { holdingColour } from "./viz";

const CASH = "USD";
const EVERY = [
  { value: "5", label: "Every week" },
  { value: "10", label: "Every 2 weeks" },
  { value: "21", label: "Every month" },
] as const;
const LENGTH = [
  { value: "126", label: "6 months" },
  { value: "252", label: "1 year" },
  { value: "504", label: "2 years" },
] as const;
type Every = (typeof EVERY)[number]["value"];
type Length = (typeof LENGTH)[number]["value"];

interface Row {
  symbol: string;
  name: string;
  percent: number;
}

const field =
  "num h-9 rounded-xl border border-line bg-white/[0.04] px-2 text-sm text-ink outline-none transition-colors focus:border-line-strong";
const short = (name: string) => name.split(" (")[0] ?? name;

function Stat({ label, figure, note }: { label: string; figure: string; note?: string }) {
  return (
    <div className="well min-w-0 px-4 py-3">
      <p className="label">{label}</p>
      <p className="num mt-1 text-xl font-semibold tracking-tight">{figure}</p>
      {note && <p className="mt-0.5 text-sm text-muted">{note}</p>}
    </div>
  );
}

/** The spread of the plan's value over time, with the money paid in as a stepped line. */
function Chart({ result }: { result: RegularBuying["result"] }) {
  const width = 600;
  const height = 170;
  const fan = result.fan as Record<string, number[]>;
  const low = fan["0.05"] ?? [];
  const high = fan["0.95"] ?? [];
  const inner = [fan["0.25"] ?? [], fan["0.75"] ?? []] as const;
  const middle = fan["0.5"] ?? [];
  const paid = result.paid_in_path;
  if (middle.length < 2) return null;
  const top = Math.max(...high, ...paid);
  const x = (i: number) => (i / (middle.length - 1)) * width;
  const y = (value: number) => height - (value / (top || 1)) * height;
  const line = (values: number[]) =>
    values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const band = (lower: number[], upper: number[]) =>
    `${line(upper)} ${lower
      .map((v, i) => `L${x(i).toFixed(1)},${y(v).toFixed(1)}`)
      .reverse()
      .join(" ")} Z`;
  return (
    <div>
      <div className="flex gap-3">
        <div className="num flex flex-col justify-between text-right text-xs text-faint">
          <span>{formatMoney(top)}</span>
          <span>{formatMoney(0)}</span>
        </div>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          className="h-44 min-w-0 flex-1"
          role="img"
          aria-label={`Value of the plan over ${result.sessions} trading days: between ${formatMoney(low.at(-1) ?? 0)} and ${formatMoney(high.at(-1) ?? 0)} at the end, against ${formatMoney(result.paid_in)} paid in`}
        >
          <path d={band(low, high)} fill="var(--accent)" opacity="0.16" />
          <path d={band(inner[0], inner[1])} fill="var(--accent)" opacity="0.3" />
          <path
            d={line(middle)}
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
          <path
            d={line(paid)}
            fill="none"
            stroke="var(--ink)"
            strokeWidth="1.5"
            strokeDasharray="4 4"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>
      <div className="mt-2 flex justify-between pl-14 text-xs text-faint">
        <span>First purchase</span>
        <span>{result.sessions} trading days</span>
      </div>
      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <span>Dashed: money paid in</span>
        <span>Line: the middle outcome</span>
        <span>Dark band: half of the outcomes</span>
        <span>Light band: 9 in 10</span>
      </p>
    </div>
  );
}

function Compare({ result }: { result: RegularBuying["result"] }) {
  const rows = [
    { key: "plan", name: "Buying bit by bit", spread: result.plan, colour: "var(--accent)" },
    { key: "once", name: "All at once on day one", spread: result.at_once, colour: "var(--gold)" },
  ];
  const quantile = (spread: (typeof rows)[number]["spread"], q: string) =>
    (spread.quantiles as Record<string, number>)[q] ?? 0;
  const reach = Math.max(...rows.map((r) => quantile(r.spread, "0.95")), result.paid_in);
  const at = (value: number) => `${(value / (reach || 1)) * 100}%`;
  return (
    <div>
      <h3 className="font-medium">Against putting it all in at once</h3>
      <ul className="mt-3 flex flex-col gap-4">
        {rows.map((row) => {
          const low = quantile(row.spread, "0.05");
          const middle = quantile(row.spread, "0.5");
          const high = quantile(row.spread, "0.95");
          return (
            <li key={row.key}>
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm">
                <span className="text-muted">{row.name}</span>
                <span className="num font-medium">
                  {formatMoney(low)} – {formatMoney(high)}{" "}
                  <span className="font-normal text-muted">middle {formatMoney(middle)}</span>
                </span>
              </div>
              <div
                className="relative mt-2 h-2 rounded-full bg-white/8"
                role="img"
                aria-label={`${row.name}: 9 in 10 outcomes between ${formatMoney(low)} and ${formatMoney(high)}`}
              >
                <span
                  className="absolute inset-y-0 rounded-full"
                  style={{
                    left: at(low),
                    right: `calc(100% - ${at(high)})`,
                    background: `color-mix(in srgb, ${row.colour} 45%, transparent)`,
                  }}
                />
                <span
                  className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-bg"
                  style={{ left: at(middle), background: row.colour }}
                />
                <span
                  className="absolute -inset-y-1 w-px bg-ink"
                  style={{ left: at(result.paid_in) }}
                  aria-hidden="true"
                />
              </div>
              <p className="mt-1.5 text-xs text-faint">
                Ended below the {formatMoney(result.paid_in)} paid in:{" "}
                {formatShare(row.spread.below_paid_in, 0)} of the time
              </p>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-sm text-muted">
        Buying bit by bit ended with more in{" "}
        <span className="num font-medium text-ink">{formatShare(result.plan_ahead, 0)}</span> of the
        simulated futures. The thin line marks the money paid in.
      </p>
    </div>
  );
}

/**
 * Regular buying: choose what to buy, how much, and how often, and see where the plan
 * might end up. Nothing is saved or bought.
 */
export function RegularBuyingPanel({
  portfolio,
  analysis,
}: {
  portfolio: Portfolio;
  analysis?: PortfolioAnalysis;
}) {
  const simulate = useRegularBuying();
  const supported = portfolio.supported.filter((a) => a.symbol !== CASH);
  // Holdings with too short a record to simulate are left out of the starting plan.
  const tooNew = new Set(
    [...(analysis?.young ?? []), ...(analysis?.unmeasured ?? [])].map((item) => item.symbol),
  );
  const held = (analysis?.positions ?? []).filter(
    (p) => p.symbol !== CASH && !tooNew.has(p.symbol),
  );
  const heldTotal = held.reduce((sum, p) => sum + p.weight, 0);
  const [rows, setRows] = useState<Row[]>(() =>
    held.length > 0 && heldTotal > 0
      ? held.map((p) => ({
          symbol: p.symbol,
          name: short(p.name),
          percent: Math.round((p.weight / heldTotal) * 100),
        }))
      : supported.slice(0, 1).map((a) => ({ symbol: a.symbol, name: short(a.name), percent: 100 })),
  );
  const [amount, setAmount] = useState("100");
  const [every, setEvery] = useState<Every>("21");
  const [length, setLength] = useState<Length>("252");

  const total = rows.reduce((sum, row) => sum + row.percent, 0);
  const dollars = Number(amount);
  const purchases = Math.floor(Number(length) / Number(every));
  const valid = total > 0 && Number.isFinite(dollars) && dollars > 0;
  const options = supported.filter((a) => !rows.some((r) => r.symbol === a.symbol));
  const found = simulate.data;
  const result = found?.result;
  const eighty = result?.coverage.find((c) => c.level === 0.8);
  const quantile = (q: string) => (result?.plan.quantiles as Record<string, number>)?.[q] ?? 0;

  function add(symbol: string, name: string) {
    setRows((before) =>
      before.some((r) => r.symbol === symbol)
        ? before
        : [...before, { symbol, name: short(name), percent: before.length === 0 ? 100 : 0 }],
    );
  }

  function run() {
    if (!valid) return;
    simulate.mutate({
      weights: Object.fromEntries(
        rows.filter((r) => r.percent > 0).map((r) => [r.symbol, r.percent]),
      ),
      amount: dollars,
      every: Number(every),
      purchases,
    });
  }

  // Open on an answer, not on an empty form: run the starting plan once.
  const started = useRef(false);
  useEffect(() => {
    if (started.current || !valid) return;
    started.current = true;
    run();
    // Only on arrival: later runs are the user's own.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Panel
      id="buying"
      title="Regular buying"
      trust={found?.trust}
      headline={
        result
          ? `${formatMoney(result.paid_in)} paid in ends between ${formatMoney(quantile("0.05"))} and ${formatMoney(quantile("0.95"))} in 9 of 10 simulated futures`
          : "Buy a fixed amount on a schedule and see where it might end up"
      }
    >
      <div className="flex flex-col gap-5">
        <div>
          <p className="label mb-2">What each purchase buys</p>
          <ul className="flex flex-col gap-2">
            {rows.map((row, i) => (
              <li key={row.symbol} className="flex items-center gap-3">
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: holdingColour(row.symbol, i) }}
                  aria-hidden="true"
                />
                <span className="min-w-0 flex-1 truncate text-sm">{row.name}</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={row.percent}
                  aria-label={`${row.name} share of each purchase, percent`}
                  onChange={(event) =>
                    setRows((before) =>
                      before.map((r) =>
                        r.symbol === row.symbol
                          ? { ...r, percent: Math.max(0, Number(event.target.value) || 0) }
                          : r,
                      ),
                    )
                  }
                  className={`${field} w-20 text-right`}
                />
                <span className="text-sm text-muted">%</span>
                <button
                  type="button"
                  aria-label={`Remove ${row.name}`}
                  onClick={() => setRows((before) => before.filter((r) => r.symbol !== row.symbol))}
                  className="h-8 w-8 rounded-full text-muted transition-colors hover:bg-white/5 hover:text-ink"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
          {rows.length > 1 && total !== 100 && total > 0 && (
            <p className="mt-2 text-xs text-faint">
              These add up to {total}%; they are scaled to 100% in the same proportions.
            </p>
          )}
        </div>

        {options.length > 0 && (
          <div>
            <p className="label mb-2">Add another asset</p>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Add another asset">
              {options.map((asset) => (
                <button
                  key={asset.symbol}
                  type="button"
                  aria-label={`Add ${short(asset.name)}`}
                  onClick={() => add(asset.symbol, asset.name)}
                  className="inline-flex items-center gap-1.5 rounded-full border border-dashed border-line-strong px-3 py-1.5 text-[13px] font-medium text-muted transition-colors hover:border-solid hover:bg-white/5 hover:text-ink"
                >
                  <span aria-hidden="true" className="text-base leading-none">
                    +
                  </span>
                  {short(asset.name)}
                </button>
              ))}
            </div>
          </div>
        )}
        <TickerBox onFound={(asset) => add(asset.symbol, asset.name)} />

        <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
          <label className="flex flex-col gap-2">
            <span className="label">Each purchase</span>
            <span className="flex items-center gap-1.5">
              <span className="text-sm text-muted">$</span>
              <input
                type="number"
                min={1}
                value={amount}
                aria-label="Dollars per purchase"
                onChange={(event) => setAmount(event.target.value)}
                className={`${field} w-28`}
              />
            </span>
          </label>
          <div className="flex flex-col gap-2">
            <span className="label">How often</span>
            <Segmented options={EVERY} value={every} onChange={setEvery} label="How often" />
          </div>
          <div className="flex flex-col gap-2">
            <span className="label">For how long</span>
            <Segmented options={LENGTH} value={length} onChange={setLength} label="For how long" />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn btn-primary disabled:opacity-50"
            disabled={!valid || simulate.isPending}
            onClick={run}
          >
            {simulate.isPending ? "Working it out…" : "See where it could end up"}
          </button>
          {valid && (
            <span className="num text-sm text-muted">
              {purchases} purchases of {formatMoney(dollars)}: {formatMoney(dollars * purchases)} in
              all
            </span>
          )}
        </div>
        {simulate.isError && (
          <p className="text-sm text-[var(--alert)]" role="alert">
            {simulate.error.message || "That plan could not be simulated."}
          </p>
        )}
      </div>

      {found && result && (
        <>
          <div className="grid grid-cols-1 gap-3 @xl:grid-cols-2 @4xl:grid-cols-4">
            <Stat
              label="Paid in"
              figure={formatMoney(result.paid_in)}
              note={`${result.purchases} purchases`}
            />
            <Stat
              label="Middle outcome"
              figure={formatMoney(quantile("0.5"))}
              note={`${formatChange(quantile("0.5") / result.paid_in - 1)} on the money paid in`}
            />
            <Stat
              label="9 in 10 end between"
              figure={`${formatMoney(quantile("0.05"))} – ${formatMoney(quantile("0.95"))}`}
            />
            <Stat
              label="Ends below what was paid in"
              figure={formatShare(result.plan.below_paid_in, 0)}
              note="of the simulated futures"
            />
          </div>
          <Chart result={result} />
          <Compare result={result} />
          {eighty && (
            <p className="text-sm text-muted">
              Checked on the past: of {eighty.n} earlier {eighty.n === 1 ? "stretch" : "stretches"}{" "}
              of this length, the range meant to hold 8 times in 10 held in{" "}
              <span className="num font-medium text-ink">{eighty.inside}</span>.
              {eighty.n < 10 && " That is very few cases, so treat the range as a rough guide."}
            </p>
          )}
          <Caption
            facts={[
              {
                label: "Shows",
                value: `${formatCount(result.n_paths)} simulated futures for this plan`,
              },
              {
                label: "Built from",
                value: `Runs of ${result.block} real trading days in a row, every asset at once`,
              },
              {
                label: "Drawn from",
                value: `${formatCount(result.n_days)} days of prices, ${formatDate(found.first_day)} to ${formatDate(found.last_day)}`,
              },
              {
                label: "The plan",
                value: `Buys ${formatMoney(result.amount)} every ${result.every} trading days and never sells`,
              },
              {
                label: "All at once",
                value: `The same ${formatMoney(result.paid_in)} on the first day, through the very same futures`,
              },
              { label: "Not counted", value: "Trading costs" },
              {
                label: "Checked",
                value:
                  "The plan simulated at earlier dates from the days before them, against how it then went",
              },
            ]}
          >
            Only about {result.separate_periods} separate{" "}
            {result.separate_periods === 1 ? "stretch" : "stretches"} of this length fit in the
            stored prices, so this shows what those years would allow, not what will happen.
          </Caption>
        </>
      )}
    </Panel>
  );
}
