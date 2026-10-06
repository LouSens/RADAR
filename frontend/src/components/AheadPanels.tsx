import { useState } from "react";

import type { PortfolioAnalysis } from "../api/client";
import { useSetTags } from "../api/queries";
import { formatChange, formatCount, formatMoney, formatShare } from "../lib/format";
import { fanShape } from "../lib/outlook";
import { formatDate } from "../lib/time";
import { Caption, Message, Panel, Segmented } from "./ui";
import { Bars, Legend, StackBar, type Part } from "./viz";

const CASH = "USD";
const HORIZONS = [
  { value: "30", label: "30 trading days" },
  { value: "90", label: "90 trading days" },
] as const;
type Steps = (typeof HORIZONS)[number]["value"];

type Simulation = NonNullable<PortfolioAnalysis["simulation"]>;
type Horizon = Simulation["horizons"][number];

function Stat({ label, figure, note }: { label: string; figure: string; note?: string }) {
  return (
    <div className="well min-w-0 px-4 py-3">
      <p className="label">{label}</p>
      <p className="num mt-1 text-xl font-semibold tracking-tight">{figure}</p>
      {note && <p className="mt-0.5 text-sm text-muted">{note}</p>}
    </div>
  );
}

function Fan({ simulation, steps }: { simulation: Simulation; steps: number }) {
  const width = 600;
  const height = 150;
  const shape = fanShape(simulation.fan as Record<string, number[]>, steps, width, height);
  if (!shape) return null;
  return (
    <div>
      <div className="flex gap-3">
        <div className="num flex flex-col justify-between text-right text-xs text-faint">
          <span>{formatMoney(shape.high)}</span>
          <span>{formatMoney(shape.low)}</span>
        </div>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          className="h-40 min-w-0 flex-1"
          role="img"
          aria-label={`Spread of simulated values widening from ${formatMoney(
            simulation.start_value,
          )} to between ${formatMoney(shape.low)} and ${formatMoney(shape.high)}`}
        >
          <path d={shape.outer} fill="var(--accent)" opacity="0.16" />
          <path d={shape.inner} fill="var(--accent)" opacity="0.3" />
          <path
            d={shape.median}
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>
      <div className="mt-2 flex justify-between pl-14 text-xs text-faint">
        <span>Today</span>
        <span>{steps} trading days</span>
      </div>
      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <span>Line: the middle outcome</span>
        <span>Dark band: half of the outcomes</span>
        <span>Light band: 9 in 10</span>
      </p>
    </div>
  );
}

/** The user picks a change in value; the app says how often the simulated futures got there. */
function ChanceCheck({ horizon, value }: { horizon: Horizon; value: number }) {
  const [percent, setPercent] = useState(-5);
  const found = horizon.chances.find((c) => Math.round(c.change * 100) === percent);
  const fall = percent < 0;
  const size = Math.abs(percent);
  const steps = horizon.summary.steps;
  const rows = found
    ? [
        {
          key: "ends",
          name: `${fall ? "Down" : "Up"} ${size}% or more at the end of ${steps} trading days`,
          value: found.ends_beyond,
          colour: fall ? "var(--alert)" : "var(--calm)",
        },
        {
          key: "touches",
          name: `${fall ? "Down" : "Up"} ${size}% or more at any point on the way`,
          value: found.touches,
          colour: fall ? "var(--alert)" : "var(--calm)",
        },
      ]
    : [];
  return (
    <div>
      <h3 className="font-medium">How likely is a change of this size?</h3>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <input
          type="range"
          min={-30}
          max={30}
          step={1}
          value={percent}
          aria-label="Change in value, percent"
          onChange={(event) => setPercent(Number(event.target.value))}
          className="min-w-40 flex-1 accent-[var(--accent)]"
        />
        <span className="num text-lg font-semibold">
          {formatChange(percent / 100).replace(".00", "")}{" "}
          <span className="text-sm font-normal text-muted">
            {formatMoney(value * (1 + percent / 100))}
          </span>
        </span>
      </div>
      <div className="mt-4">
        {percent === 0 ? (
          <p className="text-sm text-muted">Move the slider to a fall or a rise.</p>
        ) : (
          // Chances are drawn against the whole track: a full bar is every simulated future.
          <ul className="flex flex-col gap-3">
            {rows.map((row) => (
              <li
                key={row.key}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3"
              >
                <span className="min-w-0">
                  <span className="block text-xs text-muted">{row.name}</span>
                  <span className="mt-1 block h-1.5 rounded-full bg-white/8">
                    <span
                      className="block h-full rounded-full"
                      style={{ width: `${row.value * 100}%`, background: row.colour }}
                    />
                  </span>
                </span>
                <span className="num text-sm font-medium">
                  {formatShare(row.value, row.value < 0.1 ? 1 : 0)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Record({ horizon }: { horizon: Horizon }) {
  return (
    <div>
      <h3 className="font-medium">How often past ranges held</h3>
      <ul className="mt-3 flex flex-col gap-3">
        {horizon.coverage.map((row) => {
          const held = row.n > 0 ? row.inside / row.n : 0;
          return (
            <li key={row.level}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="text-muted">
                  The range meant to hold {formatShare(row.level, 0)} of the time
                </span>
                <span className="num font-medium">
                  held {row.inside} of {row.n}
                </span>
              </div>
              <div
                className="relative mt-1.5 h-1.5 rounded-full bg-white/8"
                role="img"
                aria-label={`Held ${formatShare(held, 0)} of the time against ${formatShare(row.level, 0)} stated`}
              >
                <span
                  className="block h-full rounded-full bg-[var(--accent)]"
                  style={{ width: `${held * 100}%` }}
                />
                <span
                  className="absolute -top-1 h-3.5 w-0.5 bg-ink"
                  style={{ left: `${row.level * 100}%` }}
                  aria-hidden="true"
                />
              </div>
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-xs text-faint">The marker is where each bar is meant to reach.</p>
    </div>
  );
}

export function RangeAheadPanel({ analysis }: { analysis: PortfolioAnalysis }) {
  const [steps, setSteps] = useState<Steps>("30");
  const simulation = analysis.simulation;
  if (!simulation) {
    return (
      <Panel id="ahead" title="Value range ahead">
        <Message>
          A range needs 250 trading days on which every holding has a price. These holdings do not
          share that many yet.
        </Message>
      </Panel>
    );
  }
  const horizon =
    simulation.horizons.find((h) => String(h.summary.steps) === steps) ?? simulation.horizons[0];
  if (!horizon) return null;
  const summary = horizon.summary;
  const eighty = summary.intervals.find((i) => i.level === 0.8);
  const middle = (summary.quantiles as Record<string, number>)["0.5"] ?? simulation.start_value;
  const young = analysis.young.map((item) => item.name.split(" (")[0]).join(", ");
  return (
    <Panel
      id="ahead"
      title="Value range ahead"
      trust={analysis.trust.simulation ?? undefined}
      headline={
        eighty
          ? `8 in 10 simulated futures end between ${formatMoney(eighty.low)} and ${formatMoney(eighty.high)}`
          : undefined
      }
    >
      <Segmented options={HORIZONS} value={steps} onChange={setSteps} label="How far ahead" />
      <Fan simulation={simulation} steps={summary.steps} />
      <div className="grid grid-cols-1 gap-3 @xl:grid-cols-3">
        <Stat
          label="Middle outcome"
          figure={formatMoney(middle)}
          note={`${formatChange(middle / simulation.start_value - 1)} from ${formatMoney(simulation.start_value)} today`}
        />
        <Stat
          label="8 in 10 end between"
          figure={eighty ? `${formatMoney(eighty.low)} – ${formatMoney(eighty.high)}` : "—"}
          note={
            eighty
              ? `${formatChange(eighty.low / simulation.start_value - 1)} to ${formatChange(eighty.high / simulation.start_value - 1)}`
              : undefined
          }
        />
        <Stat
          label="Typical deepest dip on the way"
          figure={formatMoney(summary.expected_worst_drawdown * simulation.start_value)}
          note={`${formatChange(summary.expected_worst_drawdown)} from a high to the low after it`}
        />
      </div>
      <ChanceCheck horizon={horizon} value={simulation.start_value} />
      <Record horizon={horizon} />
      <Caption>
        Each of {formatCount(simulation.n_paths)} simulated futures is made by joining runs of{" "}
        {simulation.block} real trading days in a row, taken from the last{" "}
        {formatCount(simulation.n_days)} days and for every holding at once, so holdings that fell
        together in the past fall together here. Your holdings are left as they are throughout and
        cash does not move. This shows what the past would allow, not what will happen: a future
        unlike anything in those {formatCount(simulation.n_days)} days is not in it.
        {simulation.scale > 1.0001 &&
          ` ${young || "A newer holding"} has too short a record to be drawn from, so every outcome is widened by ${formatShare(simulation.scale - 1, 0)} to allow for it.`}{" "}
        To check the method, a range was drawn at past dates from earlier days only and compared
        with what followed; the dates are a full {summary.steps} days apart so that no two share a
        day.
      </Caption>
    </Panel>
  );
}

const GROUP_NAME: Record<string, string> = {
  core: "Core",
  satellite: "Satellite",
  untagged: "Not tagged",
  cash: "Cash",
};
const GROUP_COLOUR: Record<string, string> = {
  core: "var(--stock)",
  satellite: "var(--btc)",
  untagged: "rgba(255,255,255,0.35)",
  cash: "var(--calm)",
};
type Tags = Record<string, "core" | "satellite" | null>;
const TAGS = [
  { value: "core", label: "Core" },
  { value: "satellite", label: "Satellite" },
  { value: "none", label: "Neither" },
] as const;

export function SleevesPanel({ analysis }: { analysis: PortfolioAnalysis }) {
  const setTags = useSetTags();
  const report = analysis.sleeves;
  const held = analysis.positions.filter((p) => p.symbol !== CASH);
  const short = (name: string) => name.split(" (")[0] ?? name;
  const satellite = report?.sleeves.find((s) => s.group === "satellite");
  const parts = (pick: (s: NonNullable<typeof report>["sleeves"][number]) => number): Part[] =>
    (report?.sleeves ?? []).map((sleeve) => ({
      key: sleeve.group,
      name: GROUP_NAME[sleeve.group] ?? sleeve.group,
      share: pick(sleeve),
      colour: GROUP_COLOUR[sleeve.group] ?? "var(--accent)",
    }));
  const money = analysis.covered_value;
  return (
    <Panel
      id="sleeves"
      title="Core and satellite"
      trust={report ? analysis.trust.xray : undefined}
      headline={
        satellite
          ? `Satellite holdings are ${formatShare(satellite.weight, 0)} of your money and ${formatShare(satellite.risk_share, 0)} of your risk`
          : "Tag your holdings to see what each group carries"
      }
    >
      <div>
        <h3 className="font-medium">Your tags</h3>
        <p className="mt-1 text-sm text-muted">
          Core is what you mean to hold steadily. Satellite is the smaller, more adventurous part.
        </p>
        <ul className="mt-3 flex flex-col">
          {held.map((position) => (
            <li
              key={position.symbol}
              className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-line py-2.5 first:border-t-0"
            >
              <span className="text-sm">
                {short(position.name)}{" "}
                <span className="num text-muted">{formatShare(position.weight, 0)}</span>
              </span>
              <Segmented
                options={TAGS}
                value={position.tag ?? "none"}
                label={`${short(position.name)} is`}
                onChange={(tag) =>
                  setTags.mutate({
                    tags: { [position.symbol]: tag === "none" ? null : tag } as Tags,
                  })
                }
              />
            </li>
          ))}
        </ul>
        {setTags.isError && (
          <p className="mt-2 text-sm text-[var(--alert)]">That tag could not be saved.</p>
        )}
      </div>

      {report && (
        <>
          <div className="flex flex-col gap-4">
            <div>
              <p className="label mb-2">Share of your money</p>
              <StackBar parts={parts((s) => s.weight)} label="Share of your money" />
            </div>
            <div>
              <p className="label mb-2">Share of your risk</p>
              <StackBar parts={parts((s) => s.risk_share)} label="Share of your risk" />
            </div>
            <Legend parts={parts((s) => s.weight)} />
          </div>
          <div>
            <h3 className="font-medium">
              What each group added over the last {formatCount(report.n_days)} trading days
            </h3>
            <div className="mt-3">
              <Bars
                rows={report.sleeves
                  .filter((s) => s.group !== "cash")
                  .map((sleeve) => ({
                    key: sleeve.group,
                    name: GROUP_NAME[sleeve.group] ?? sleeve.group,
                    value: sleeve.contribution,
                    colour: sleeve.contribution < 0 ? "var(--alert)" : GROUP_COLOUR[sleeve.group],
                  }))}
                format={(value) => `${formatChange(value)} · ${formatMoney(value * money)}`}
              />
            </div>
            <p className="num mt-3 text-sm text-muted">
              All together {formatChange(report.total_return)}
            </p>
          </div>
          <Caption>
            Risk shares are from the Risk by holding page and add up to 100%. The amounts added are
            for today&apos;s proportions held from {formatDate(report.first_day)} to{" "}
            {formatDate(report.last_day)}: each holding&apos;s share of your money times the sum of
            its daily changes. That is how today&apos;s mix would have done, not what you earned;
            RADAR does not know when you bought. Money figures are for {formatMoney(money)} at
            today&apos;s value.
            {report.short.length > 0 &&
              ` ${report.short.map((s) => short(analysis.positions.find((p) => p.symbol === s)?.name ?? s)).join(", ")} has fewer days of prices, so its part covers only the days it has.`}
          </Caption>
        </>
      )}
    </Panel>
  );
}
