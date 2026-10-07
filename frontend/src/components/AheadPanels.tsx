import { useState } from "react";

import type { PortfolioAnalysis } from "../api/client";
import { formatChange, formatCount, formatMoney, formatShare } from "../lib/format";
import { fanShape } from "../lib/outlook";
import { Caption, Evidence, Message, Panel, Segmented } from "./ui";

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
      <ul className="flex flex-col gap-3">
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
  const plain = horizon.baseline_coverage?.find((c) => c.level === 0.8);
  const ours = horizon.coverage.find((c) => c.level === 0.8);
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
      <Evidence summary="How often past ranges held">
        <Record horizon={horizon} />
      </Evidence>
      <Caption
        facts={[
          {
            label: "Shows",
            value: `${formatCount(simulation.n_paths)} simulated futures for today's holdings`,
          },
          {
            label: "Built from",
            value: `Runs of ${simulation.block} real trading days in a row, every holding at once, so holdings that fell together then fall together here`,
          },
          { label: "Drawn from", value: `The last ${formatCount(simulation.n_days)} trading days` },
          { label: "Assumes", value: "Holdings left as they are throughout; cash does not move" },
          ...(simulation.scale > 1.0001
            ? [
                {
                  label: "Widened",
                  value: `By ${formatShare(simulation.scale - 1, 0)}: ${young || "a newer holding"} has too short a record to draw from`,
                },
              ]
            : []),
          {
            label: "Checked",
            value: `Ranges drawn at past dates from earlier days only, ${summary.steps} days apart so no two share a day`,
          },
          ...(plain
            ? [
                {
                  label: "Against a bell curve",
                  value: `Its 80% range held ${plain.inside} of ${plain.n}; this one ${ours?.inside ?? 0} of ${ours?.n ?? 0}`,
                },
              ]
            : []),
        ]}
      >
        This shows what the past would allow, not what will happen: a future unlike anything in
        those days is not in it.
        {plain
          ? " The simulation is shown because it assumes no bell curve and also gives the dips along the way, not because its range has proved more accurate."
          : ""}
      </Caption>
    </Panel>
  );
}
